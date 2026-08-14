"""IMAX 회차 판별."""

from __future__ import annotations

from ..domain.models import Screening

IMAX_GRADE_CD = "03"  # tcscnsGradCd 실측값 ("아이맥스")


class ImaxFilter:
    def is_imax(self, screening: Screening) -> bool:
        return screening.grade_cd == IMAX_GRADE_CD or "IMAX" in screening.screen_name.upper()

    def filter(self, screenings: list[Screening]) -> list[Screening]:
        return [s for s in screenings if self.is_imax(s)]
