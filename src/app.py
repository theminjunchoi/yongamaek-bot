"""폴링 루프 오케스트레이션."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .backoff import BackoffPolicy
from .config import Config
from .detector import OpeningDetector
from .imax_filter import ImaxFilter
from .notifier import Notifier, NotifyError
from .schedule_source import ScheduleFetchError, ScheduleSource
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
    ):
        self._source = source
        self._filter = imax_filter
        self._store = store
        self._detector = detector
        self._notifier = notifier
        self._config = config
        self._backoff = BackoffPolicy()
        self._alerted_failure = False

    def run_forever(self) -> None:
        logger.info(
            "폴링 시작: siteNo=%s, 간격 %.0f초 (심야 %.0f초), %d일치 조회",
            self._config.site_no,
            self._config.poll_interval_sec,
            self._config.night_poll_interval_sec,
            self._config.days_ahead,
        )
        while True:
            delay = self._run_cycle_guarded()
            time.sleep(delay)

    def run_once(self) -> list:
        """1회 조회 모드: 현재 열려있는 IMAX 회차 전체를 출력한다. 상태 변경 없음."""
        screenings = self._fetch_all_imax()
        self._notifier.notify_openings(screenings)
        return screenings

    def _run_cycle_guarded(self) -> float:
        """사이클을 실행하고 다음 대기시간(초)을 반환한다."""
        try:
            self._run_cycle()
        except ScheduleFetchError as e:
            delay = self._backoff.record_failure()
            logger.warning(
                "사이클 실패(연속 %d회): %s — %.0f초 후 재시도",
                self._backoff.consecutive_failures,
                e,
                delay,
            )
            if (
                self._backoff.consecutive_failures >= self._config.alert_after_failures
                and not self._alerted_failure
            ):
                self._notifier.alert(
                    f"용아맥 봇 장애: 스케줄 조회 연속 {self._backoff.consecutive_failures}회 실패 ({e})"
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
        current = self._fetch_all_imax()

        if not self._store.exists():
            # 첫 실행: 기존 회차 전체가 신규로 오인되지 않도록 알림 없이 스냅샷만 구축
            self._store.save({s.key for s in current})
            logger.info("초기 스냅샷 구축: 회차 %d건 (알림 생략)", len(current))
            return

        known = self._store.load()
        new_screenings = self._detector.detect(known, current)

        if new_screenings:
            logger.info("신규 오픈 감지: %d건", len(new_screenings))
            self._notifier.notify_openings(new_screenings)  # 실패 시 예외 → 스냅샷 미저장
            known |= {s.key for s in new_screenings}

        today = datetime.now(KST).strftime("%Y%m%d")
        self._store.save(self._detector.prune_expired(known, today))

    def _fetch_all_imax(self) -> list:
        """오늘부터 days_ahead일치를 조회해 IMAX 회차만 모은다.

        일부 날짜 실패는 건너뛰되, 전부 실패하면 사이클 실패로 본다.
        """
        screenings = []
        errors: list[ScheduleFetchError] = []
        dates = self._dates_to_check()
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

    def _current_interval(self) -> float:
        hour = datetime.now(KST).hour
        if NIGHT_START_HOUR <= hour < NIGHT_END_HOUR:
            return self._config.night_poll_interval_sec
        return self._config.poll_interval_sec
