"""좌석 도메인 모델과 좌석 구역(zone) 판별.

좌석맵 API(searchIfSeatData)가 좌석 단위 상태를 준다. 상태 코드 의미는
2026-08-16 실측으로 확정했다 (scnYmd별 frSeatCnt와 58/58 일치 검증):

- seatStusCd "01" (판매)  = 이미 팔린 좌석
- seatStusCd "00" (미정)  + seatSaleYn "Y" = 예매 가능  ← 잔여석
- seatStusCd "00" (미정)  + seatSaleYn "N" = 상시 차단석 (용아맥 K16~K19)
- seatStusCd "04" (진행)  = 결제 진행 중 임시 점유

따라서 "예매 가능"의 유일한 판별 기준은 seatSaleYn == "Y" 이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Seat:
    """좌석 하나. 불변 객체."""

    loc_no: str  # seatLocNo, 상영관 내 고유 식별자
    row: str  # seatRowNm, 예: "J"
    number: int  # seatNo, 예: 23
    status_cd: str  # seatStusCd
    sale_yn: str  # seatSaleYn

    @property
    def label(self) -> str:
        """표시·비교용 좌석 이름. 예: "J23"."""
        return f"{self.row}{self.number}"

    @property
    def is_available(self) -> bool:
        return self.sale_yn == "Y"

    @classmethod
    def from_api(cls, row: dict) -> "Seat":
        """searchIfSeatData 응답의 seats 원소 하나를 모델로 변환한다."""
        return cls(
            loc_no=str(row.get("seatLocNo", "")),
            row=str(row.get("seatRowNm", "")),
            number=int(str(row.get("seatNo", "0")) or 0),
            status_cd=str(row.get("seatStusCd", "")),
            sale_yn=str(row.get("seatSaleYn", "")),
        )


class SeatZone(ABC):
    """좌석 구역 판별 (OCP 확장점).

    "명당" 정의를 바꾸거나 상영관별로 다른 구역을 쓰려면 구현체만 갈아끼운다.
    """

    @property
    @abstractmethod
    def label(self) -> str:
        """알림에 쓰이는 구역 이름."""

    @abstractmethod
    def contains(self, seat: Seat) -> bool:
        """좌석이 이 구역에 속하는지."""

    def filter(self, seats: list[Seat]) -> list[Seat]:
        return [s for s in seats if self.contains(s)]


@dataclass(frozen=True)
class RowRangeZone(SeatZone):
    """"H~L열의 16~29번"처럼 열 집합 × 번호 범위로 정의되는 구역."""

    rows: frozenset
    min_number: int
    max_number: int
    zone_label: str = "명당"

    @property
    def label(self) -> str:
        return self.zone_label

    def contains(self, seat: Seat) -> bool:
        return seat.row in self.rows and self.min_number <= seat.number <= self.max_number

    @classmethod
    def of(cls, rows: str, min_number: int, max_number: int, label: str = "명당") -> "RowRangeZone":
        return cls(frozenset(rows), min_number, max_number, label)


# 용아맥(용산 IMAX관, 624석) 명당: H~L열 16~29번 = 70석.
# 이 중 K16~K19 4석은 상시 차단석이라 실제 감시 대상은 66석이다.
YONGSAN_IMAX_HONEY = RowRangeZone.of("HIJKL", 16, 29)


def group_consecutive(seats: list[Seat]) -> list[list[Seat]]:
    """같은 열의 연속 번호끼리 묶는다. 연석 여부가 명당 알림의 핵심 정보다.

    예: [J23, J24, L20] -> [[J23, J24], [L20]]
    """
    runs: list[list[Seat]] = []
    for seat in sorted(seats, key=lambda s: (s.row, s.number)):
        if runs and runs[-1][-1].row == seat.row and runs[-1][-1].number == seat.number - 1:
            runs[-1].append(seat)
        else:
            runs.append([seat])
    return runs


def format_runs(seats: list[Seat]) -> str:
    """연석을 묶어 사람이 읽는 문자열로. 예: "J23~J24 (2연석), L20"."""
    parts = []
    for run in group_consecutive(seats):
        if len(run) == 1:
            parts.append(run[0].label)
        else:
            parts.append(f"{run[0].label}~{run[-1].label} ({len(run)}연석)")
    return ", ".join(parts)
