"""폴링 루프 오케스트레이션."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from typing import Optional

from ..domain.config import Config
from ..notify.notifier import Notifier, NotifyError
from ..notify.pattern_logger import OpeningPatternLogger
from ..sources.imax_filter import ImaxFilter
from ..sources.schedule_source import ScheduleFetchError, ScheduleSource
from .backoff import BackoffPolicy
from .detector import OpeningDetector
from .snapshot_store import JsonSnapshotStore

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
NIGHT_START_HOUR = 1
NIGHT_END_HOUR = 7


class MonitorApp:
    def __init__(
        self,
        source: ScheduleSource,
        imax_filter: ImaxFilter,
        store: JsonSnapshotStore,
        detector: OpeningDetector,
        notifier: Notifier,
        config: Config,
        pattern_logger: Optional[OpeningPatternLogger] = None,
        theater_name: str = "용아맥",
    ):
        self._source = source
        self._filter = imax_filter
        self._store = store
        self._detector = detector
        self._notifier = notifier
        self._config = config
        self._pattern_logger = pattern_logger
        self._theater_name = theater_name
        self._backoff = BackoffPolicy()
        self._alerted_failure = False
        self._last_full_sweep = 0.0

    @property
    def theater_name(self) -> str:
        return self._theater_name

    def step(self) -> float:
        """사이클 한 번을 실행하고 다음 실행까지의 대기시간(초)을 반환한다."""
        return self._run_cycle_guarded()

    def run_once(self) -> list:
        """1회 조회 모드: 현재 열려있는 IMAX 회차 전체를 출력한다. 상태 변경 없음."""
        screenings = self._fetch_imax(self._dates_to_check())
        self._notifier.notify_openings(screenings)
        return screenings

    def _run_cycle_guarded(self) -> float:
        """사이클을 실행하고 다음 대기시간(초)을 반환한다."""
        try:
            self._run_cycle()
        except ScheduleFetchError as e:
            delay = self._backoff.record_failure()
            logger.warning(
                "[%s] 사이클 실패(연속 %d회): %s — %.0f초 후 재시도",
                self._theater_name,
                self._backoff.consecutive_failures,
                e,
                delay,
            )
            if (
                self._backoff.consecutive_failures >= self._config.alert_after_failures
                and not self._alerted_failure
            ):
                self._notifier.alert(
                    f"[{self._theater_name}] 봇 장애: 스케줄 조회 연속 "
                    f"{self._backoff.consecutive_failures}회 실패 ({e})"
                )
                self._alerted_failure = True
            return delay
        except NotifyError as e:
            # 알림 실패 시 스냅샷을 저장하지 않았으므로 다음 사이클에 자동 재시도된다.
            logger.warning("알림 발송 실패, 다음 사이클에 재시도: %s", e)
            return self._current_interval()

        self._backoff.reset()
        self._alerted_failure = False
        return self._current_interval()

    def _run_cycle(self) -> None:
        if not self._store.exists():
            # 첫 실행: 기존 회차 전체가 신규로 오인되지 않도록 알림 없이 스냅샷만 구축
            current = self._fetch_imax(self._dates_to_check())
            self._store.save({s.key for s in current})
            self._last_full_sweep = time.monotonic()
            logger.info("[%s] 초기 스냅샷 구축: 회차 %d건 (알림 생략)", self._theater_name, len(current))
            return

        known = self._store.load()

        # 매 사이클은 "마지막 오픈 날짜 이후"만 빠르게 보고(새 날짜 오픈 감지),
        # 주기적으로만 전체 범위를 스캔한다(열린 날짜에 새 영화가 편성되는 경우 감지).
        full = time.monotonic() - self._last_full_sweep >= self._config.full_sweep_interval_sec
        dates = self._dates_to_check() if full else self._frontier_dates(known)
        current = self._fetch_imax(dates)
        if full:
            self._last_full_sweep = time.monotonic()

        new_screenings = self._detector.detect(known, current)

        if new_screenings:
            logger.info("[%s] 신규 오픈 감지: %d건", self._theater_name, len(new_screenings))
            self._notifier.notify_openings(new_screenings)  # 실패 시 예외 → 스냅샷 미저장
            if self._pattern_logger is not None:
                self._pattern_logger.record(new_screenings)
            known |= {s.key for s in new_screenings}

        today = datetime.now(KST).strftime("%Y%m%d")
        self._store.save(self._detector.prune_expired(known, today))

    def _fetch_imax(self, dates: list) -> list:
        """주어진 날짜들을 조회해 IMAX 회차만 모은다.

        일부 날짜 실패는 건너뛰되, 전부 실패하면 사이클 실패로 본다.
        """
        screenings = []
        errors: list[ScheduleFetchError] = []
        for i, date in enumerate(dates):
            if i > 0:
                time.sleep(
                    random.uniform(
                        self._config.request_delay_min_sec, self._config.request_delay_max_sec
                    )
                )
            try:
                screenings.extend(self._filter.filter(self._source.fetch(date)))
            except ScheduleFetchError as e:
                errors.append(e)
                logger.debug("날짜 %s 조회 실패: %s", date, e)

        if errors and len(errors) == len(dates):
            raise errors[0]
        return screenings

    def _dates_to_check(self) -> list[str]:
        today = datetime.now(KST).date()
        return [(today + timedelta(days=n)).strftime("%Y%m%d") for n in range(self._config.days_ahead)]

    def _frontier_dates(self, known_keys: set) -> list[str]:
        """스냅샷의 마지막 오픈 날짜 다음 날부터 frontier_ahead일치를 반환한다."""
        today_str = datetime.now(KST).strftime("%Y%m%d")
        last_open = max((k.split("|", 1)[0] for k in known_keys), default=today_str)
        base = max(last_open, today_str)
        base_date = datetime.strptime(base, "%Y%m%d").date()
        return [
            (base_date + timedelta(days=n)).strftime("%Y%m%d")
            for n in range(1, self._config.frontier_ahead + 1)
        ]

    def _current_interval(self) -> float:
        hour = datetime.now(KST).hour
        if NIGHT_START_HOUR <= hour < NIGHT_END_HOUR:
            return self._config.night_poll_interval_sec
        return self._config.poll_interval_sec


class MonitorCoordinator:
    """여러 극장 모니터를 각자의 주기로 독립 실행한다.

    각 극장은 자기 백오프·간격에 따라 다음 실행 시각을 갖고, 코디네이터는
    실행할 때가 된 극장만 순회 실행한다. (극장 하나의 실패가 다른 극장에 영향 없음)
    """

    def __init__(self, monitors: list, max_runtime_sec: float = 0.0):
        self._monitors = monitors
        self._max_runtime_sec = max_runtime_sec

    def run_forever(self) -> None:
        logger.info("감시 시작: 극장 %d곳 (%s)", len(self._monitors),
                    ", ".join(m.theater_name for m in self._monitors))
        started = time.monotonic()
        next_run = {m: 0.0 for m in self._monitors}
        while True:
            if self._max_runtime_sec and time.monotonic() - started >= self._max_runtime_sec:
                logger.info("최대 실행 시간(%.0f초) 도달, 정상 종료", self._max_runtime_sec)
                return
            now = time.monotonic()
            for monitor in self._monitors:
                if now >= next_run[monitor]:
                    delay = monitor.step()
                    next_run[monitor] = time.monotonic() + delay
            # 다음 실행 예정까지 대기하되, 종료시간 체크 응답성을 위해 상한을 둔다.
            sleep_for = min(next_run.values()) - time.monotonic()
            time.sleep(max(1.0, min(sleep_for, 15.0)))
