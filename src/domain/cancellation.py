"""취소표 감지 이벤트.

"특정 회차에서, 구역(명당) 안의 좌석이 새로 예매 가능해졌다"는 사실 하나를
표현한다. 같은 사이클에 여러 좌석이 함께 풀리면 한 이벤트로 묶인다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Screening
from .seat import Seat, format_runs, group_consecutive


@dataclass(frozen=True)
class Cancellation:
    screening: Screening
    seats: tuple  # (Seat, ...) 새로 예매 가능해진 구역 내 좌석
    zone_label: str = "명당"

    @property
    def seat_text(self) -> str:
        """연석 표기를 포함한 전체 문자열. 예: "J23~J24 (2연석), L20"."""
        return format_runs(list(self.seats))

    @property
    def seat_summary(self) -> str:
        """좌석 범위만 압축한 문자열. 예: "J23~J24, L20"."""
        parts = []
        for run in group_consecutive(list(self.seats)):
            parts.append(run[0].label if len(run) == 1 else f"{run[0].label}~{run[-1].label}")
        return ", ".join(parts)

    @property
    def seat_headline(self) -> str:
        """알림 제목용 한 줄. 연석이면 그 사실이 제일 먼저 보여야 한다.

        낱좌석 1개  -> "J23"
        전부 연속    -> "J23~J24 (2연석)"
        흩어진 경우  -> "J23~J24, L20 (3석)"
        """
        count = len(self.seats)
        if count <= 1:
            return self.seat_summary
        if self.max_run_length == count:
            return f"{self.seat_summary} ({count}연석)"
        return f"{self.seat_summary} ({count}석)"

    @property
    def run_detail(self) -> str:
        """좌석 필드 보조 설명. 낱좌석 하나뿐이면 빈 문자열."""
        count = len(self.seats)
        if count <= 1:
            return ""
        if self.max_run_length == count:
            return f"나란한 {count}자리"
        if self.max_run_length >= 2:
            return f"총 {count}석 · 최대 {self.max_run_length}연석"
        return f"총 {count}석 · 떨어진 자리"

    @property
    def max_run_length(self) -> int:
        """가장 긴 연석의 길이. 1이면 낱좌석뿐이다."""
        runs = group_consecutive(list(self.seats))
        return max((len(r) for r in runs), default=0)

    @property
    def seat_labels(self) -> list:
        return [s.label for s in sorted(self.seats, key=lambda s: (s.row, s.number))]
