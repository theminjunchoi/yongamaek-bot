"""직전 관측과 현재 좌석 상태의 diff로 새로 나온 좌석을 가려낸다."""

from __future__ import annotations


class CancellationDetector:
    def detect_new(self, previous_labels: set, current_available: list) -> list:
        """직전에 없다가 지금 예매 가능해진 좌석만 반환한다.

        previous_labels가 비어 있어도(=직전에 구역 전체 매진) 그대로 동작한다.
        최초 관측(직전 기록 자체가 없는 경우)은 호출자가 걸러야 한다.
        예매 오픈 직후에는 구역 전체가 비어 있어 전 좌석이 "신규"가 되기 때문이다.
        """
        return [s for s in current_available if s.label not in previous_labels]

    def available_in_zone(self, seats: list, zone) -> list:
        """좌석 전량 중 구역 안의 예매 가능 좌석만 추린다."""
        return [s for s in seats if s.is_available and zone.contains(s)]
