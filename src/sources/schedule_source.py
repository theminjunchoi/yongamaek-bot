"""상영 스케줄 데이터 소스 추상화 (OCP 확장점).

HTTP 직접 폴링이 막히면 Playwright 기반 구현을 추가하는 식으로,
기존 코드를 수정하지 않고 구현체만 교체할 수 있다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Screening


class ScheduleFetchError(Exception):
    """스케줄 조회 실패. status 코드가 있으면 담는다."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ScheduleSource(ABC):
    """특정 극장의 하루치 상영 스케줄을 가져온다."""

    @abstractmethod
    def fetch(self, date: str) -> list[Screening]:
        """date(YYYYMMDD)의 전체 회차 목록을 반환한다.

        예매 미오픈 날짜는 빈 리스트를 반환한다.
        실패 시 ScheduleFetchError를 던진다.
        """
