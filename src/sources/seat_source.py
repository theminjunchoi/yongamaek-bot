"""좌석맵 데이터 소스 추상화 (OCP 확장점).

스케줄 소스(ScheduleSource)와 별개 포트로 둔다. 좌석맵 조회가 막혀도
예매 오픈 감지는 계속 동작해야 하므로 실패 타입도 분리한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.seat import Seat


class SeatFetchError(Exception):
    """좌석맵 조회 실패. status 코드가 있으면 담는다."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SeatSource(ABC):
    """상영 회차 하나의 좌석 상태 전량을 가져온다."""

    @abstractmethod
    def fetch(self, date: str, screen_no: str, seq: str) -> list[Seat]:
        """date(YYYYMMDD)·상영관·회차의 좌석 목록을 반환한다.

        실패 시 SeatFetchError를 던진다.
        """
