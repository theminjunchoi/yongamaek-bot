"""도메인 모델. CGV API 응답의 회차 한 건을 표현한다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Screening:
    """상영 회차 하나. 불변 객체."""

    site_no: str
    screen_no: str
    screen_name: str
    grade_cd: str  # tcscnsGradCd, IMAX는 "03"
    movie_no: str
    movie_name: str
    product_name: str  # 포맷 포함 상품명 (예: "오디세이(IMAX LASER 2D)")
    date: str  # YYYYMMDD
    seq: str  # 회차 번호 (scnSseq)
    start_time: str  # HHMM (심야는 "2500"식 24+ 표기)
    end_time: str  # HHMM
    remaining_seats: int
    total_seats: int
    rating: str

    @property
    def key(self) -> str:
        """스냅샷 diff의 기준 키: 영화×날짜.

        "새 날짜(또는 새 영화)의 예매 오픈"만 알리고, 이미 열린 날짜에
        같은 영화의 회차가 추가되는 것은 알리지 않기 위해 회차 단위가 아닌
        영화×날짜 단위로 잡는다. 날짜가 앞에 와야 지난 키 정리가 동작한다.
        """
        return f"{self.date}|{self.movie_no}"

    @property
    def start_time_display(self) -> str:
        """"0730" -> "07:30", "2500" -> "25:00" 형태로 표시용 변환."""
        t = self.start_time.zfill(4)
        return f"{t[:2]}:{t[2:]}"

    @property
    def date_display(self) -> str:
        """"20260814" -> "2026-08-14"."""
        d = self.date
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"

    @property
    def date_display_ko(self) -> str:
        """"20260826" -> "8월 26일 (수)"."""
        from datetime import datetime

        dt = datetime.strptime(self.date, "%Y%m%d")
        weekday = "월화수목금토일"[dt.weekday()]
        return f"{dt.month}월 {dt.day}일 ({weekday})"

    @classmethod
    def from_api(cls, row: dict) -> "Screening":
        """searchMovScnInfo 응답의 행 하나를 모델로 변환한다."""

        def _int(value: object) -> int:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return 0

        return cls(
            site_no=str(row.get("siteNo", "")),
            screen_no=str(row.get("scnsNo", "")),
            screen_name=str(row.get("scnsNm", "")),
            grade_cd=str(row.get("tcscnsGradCd", "")),
            movie_no=str(row.get("movNo", "")),
            movie_name=str(row.get("movNm", "")),
            product_name=str(row.get("expoProdNm", "") or row.get("movNm", "")),
            date=str(row.get("scnYmd", "")),
            seq=str(row.get("scnSseq", "")),
            start_time=str(row.get("scnsrtTm", "")),
            end_time=str(row.get("scnendTm", "")),
            remaining_seats=_int(row.get("frSeatCnt")),
            total_seats=_int(row.get("stcnt")),
            rating=str(row.get("cratgClsNm", "")),
        )
