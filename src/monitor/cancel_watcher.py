"""명당 취소표 감시.

좌석맵은 회차당 약 36KB(gzip)라 58회차를 매분 전수 조회하면 요청량이
현행의 15~20배가 된다. CGV 서버가 버티느냐가 아니라 WAF에 찍혀 러너 IP가
차단되면 봇 전체가 죽는 게 문제다. 그래서 게이트 방식을 쓴다.

  1) 스케줄 API 1요청이 그 날짜 전 회차의 frSeatCnt를 통째로 준다.
     (오픈 감지가 이미 받아오는 데이터라 추가 요청이 0건이다)
  2) 잔여석 수가 직전 사이클과 달라진 회차만 좌석맵을 조회한다.
  3) 그것만으로는 "같은 사이클 안에 취소 +1과 구매 -1이 상쇄"된 경우를
     놓치므로, 매 사이클 몇 회차씩 순번대로 좌석맵을 갈아본다(롤링 스윕).

최초 관측 회차는 기준선만 잡고 알리지 않는다. 예매가 갓 열린 날짜는
명당이 통째로 비어 있어서, 알렸다간 66석이 한꺼번에 취소표로 둔갑한다.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from ..domain.cancellation import Cancellation
from ..domain.seat import SeatZone
from ..notify.notifier import NotifyError
from ..sources.seat_source import SeatFetchError, SeatSource
from .cancel_detector import CancellationDetector
from .seat_snapshot_store import JsonSeatSnapshotStore

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


class CancelWatcher:
    def __init__(
        self,
        seat_source: SeatSource,
        zone: SeatZone,
        store: JsonSeatSnapshotStore,
        detector: CancellationDetector,
        notifier,
        sweep_per_cycle: int = 6,  # 롤링 스윕: 매 사이클 갈아볼 회차 수
        max_fetch_per_cycle: int = 25,  # 사이클당 좌석맵 조회 상한 (1분 주기 보호)
        request_delay_min_sec: float = 0.3,
        request_delay_max_sec: float = 0.6,
        alert_after_failures: int = 5,
        alert=None,
        theater_name: str = "용아맥",
    ):
        self._source = seat_source
        self._zone = zone
        self._store = store
        self._detector = detector
        self._notifier = notifier
        self._sweep_per_cycle = sweep_per_cycle
        self._max_fetch_per_cycle = max_fetch_per_cycle
        self._delay_min = request_delay_min_sec
        self._delay_max = request_delay_max_sec
        self._alert_after_failures = alert_after_failures
        self._alert = alert
        self._theater_name = theater_name
        self._cursor = 0
        self._consecutive_failures = 0
        self._alerted_failure = False

    def observe(self, screenings: list) -> None:
        """한 사이클치 IMAX 회차 목록을 받아 취소표를 감지하고 알린다.

        예매 오픈 감지를 방해하면 안 되므로 예외를 밖으로 던지지 않는다.
        """
        eligible = self._eligible(screenings)
        if not eligible:
            return

        state = self._store.load()
        targets = self._pick_targets(eligible, state)
        if not targets:
            return

        cancellations = []
        updates = {}
        for i, screening in enumerate(targets):
            if i > 0:
                time.sleep(random.uniform(self._delay_min, self._delay_max))
            observed = self._observe_one(screening, state)
            if observed is None:
                continue
            available_labels, cancellation = observed
            updates[screening.screening_key] = {
                "free": screening.remaining_seats,
                "honey": available_labels,
            }
            if cancellation is not None:
                cancellations.append(cancellation)

        if cancellations:
            logger.info(
                "[%s] %s 취소표 감지: %d회차 (%s)",
                self._theater_name,
                self._zone.label,
                len(cancellations),
                ", ".join(f"{c.screening.date} {c.seat_text}" for c in cancellations),
            )
            try:
                self._notifier.notify_cancellations(cancellations)
            except NotifyError as e:
                # 상태를 저장하지 않으므로 다음 사이클에 같은 좌석이 다시 잡힌다.
                logger.warning("취소표 알림 발송 실패, 다음 사이클에 재시도: %s", e)
                return

        state.update(updates)
        today = datetime.now(KST).strftime("%Y%m%d")
        self._store.save(self._store.prune_expired(state, today))

    def _eligible(self, screenings: list) -> list:
        """아직 예매할 수 있는 회차만 감시한다.

        기준은 판매 종료 시각(salEndTm)이다. 실측상 항상 상영시작+15분이라
        상영이 막 시작된 회차도 15분간은 예매가 열려 있고, 그 사이의 취소표는
        여전히 잡을 수 있는 자리다. 반대로 판매가 끝난 회차는 알려봐야 소용없다.
        """
        now = datetime.now(KST)
        eligible = {}
        for s in screenings:
            # 같은 회차가 중복으로 들어오면 두 번 알릴 수 있으므로 키로 접는다.
            if s.is_booking_open(now):
                eligible.setdefault(s.screening_key, s)
        return list(eligible.values())

    def _pick_targets(self, eligible: list, state: dict) -> list:
        """좌석맵을 조회할 회차를 고른다: 잔여석 변동분 + 최초 관측분 + 롤링 스윕."""
        targets = []
        picked = set()
        rest = []
        for screening in eligible:
            previous = state.get(screening.screening_key)
            if previous is None or previous.get("free") != screening.remaining_seats:
                targets.append(screening)
                picked.add(screening.screening_key)
            else:
                rest.append(screening)

        if rest and self._sweep_per_cycle > 0:
            start = self._cursor % len(rest)
            rotated = rest[start:] + rest[:start]
            for screening in rotated[: self._sweep_per_cycle]:
                if screening.screening_key not in picked:
                    targets.append(screening)
                    picked.add(screening.screening_key)
            self._cursor = start + self._sweep_per_cycle

        if len(targets) > self._max_fetch_per_cycle:
            logger.info(
                "[%s] 좌석맵 조회 대상 %d회차 → 상한 %d회차로 절삭 (나머지는 다음 사이클)",
                self._theater_name,
                len(targets),
                self._max_fetch_per_cycle,
            )
            targets = targets[: self._max_fetch_per_cycle]
        return targets

    def _observe_one(self, screening, state: dict) -> Optional[tuple]:
        """회차 하나의 좌석맵을 조회해 (구역 가용 좌석 라벨, 취소 이벤트)를 만든다."""
        try:
            seats = self._source.fetch(screening.date, screening.screen_no, screening.seq)
        except SeatFetchError as e:
            self._record_failure(e)
            return None

        self._record_success()
        available = self._detector.available_in_zone(seats, self._zone)
        labels = sorted(s.label for s in available)

        previous = state.get(screening.screening_key)
        if previous is None:
            # 최초 관측: 기준선만 잡고 알리지 않는다.
            return labels, None

        new_seats = self._detector.detect_new(set(previous.get("honey") or []), available)
        if not new_seats:
            return labels, None

        return labels, Cancellation(
            screening=screening,
            seats=tuple(sorted(new_seats, key=lambda s: (s.row, s.number))),
            zone_label=self._zone.label,
        )

    def _record_failure(self, error: SeatFetchError) -> None:
        self._consecutive_failures += 1
        logger.warning(
            "좌석맵 조회 실패(연속 %d회): %s", self._consecutive_failures, error
        )
        if (
            self._consecutive_failures >= self._alert_after_failures
            and not self._alerted_failure
            and self._alert is not None
        ):
            self._alert(
                f"[{self._theater_name}] {self._zone.label} 취소표 감시 장애: "
                f"좌석맵 조회 연속 {self._consecutive_failures}회 실패 ({error})"
            )
            self._alerted_failure = True

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._alerted_failure = False
