"""취소표 알림 채널 추상화 (OCP 확장점).

기존 Notifier(예매 오픈 알림)를 건드리지 않고 별도 포트로 둔다.
오픈 알림과 취소 알림은 채널도 다르고 메시지 형식도 다르기 때문이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CancellationNotifier(ABC):
    @abstractmethod
    def notify_cancellations(self, cancellations: list) -> None:
        """새로 나온 구역 내 좌석들을 알린다. 실패 시 NotifyError를 던진다."""


class ConsoleCancellationNotifier(CancellationNotifier):
    """--once 모드 등 로컬 확인용."""

    def notify_cancellations(self, cancellations: list) -> None:
        for c in cancellations:
            s = c.screening
            print(
                f"[{c.zone_label}] {s.product_name} | {s.date_display} "
                f"{s.start_time_display} | {c.seat_text}"
            )
