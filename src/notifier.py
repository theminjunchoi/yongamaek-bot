"""알림 채널 추상화 (OCP 확장점).

2단계에서 구독자 개인 멘션 등 새 알림 방식이 필요하면
Notifier 구현체를 추가한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Screening


class NotifyError(Exception):
    """알림 발송 실패."""


class Notifier(ABC):
    @abstractmethod
    def notify_openings(self, screenings: list[Screening]) -> None:
        """신규 오픈 회차들을 알린다. 실패 시 NotifyError를 던진다."""

    @abstractmethod
    def alert(self, message: str) -> None:
        """봇 장애 등 운영 경고를 알린다. 실패해도 예외를 밖으로 던지지 않는다."""


class ConsoleNotifier(Notifier):
    """--once 모드 등 로컬 확인용."""

    def notify_openings(self, screenings: list[Screening]) -> None:
        for s in screenings:
            print(
                f"[IMAX] {s.product_name} | {s.date_display} {s.start_time_display}"
                f" | 잔여 {s.remaining_seats}/{s.total_seats} | {s.screen_name}"
            )

    def alert(self, message: str) -> None:
        print(f"[경고] {message}")
