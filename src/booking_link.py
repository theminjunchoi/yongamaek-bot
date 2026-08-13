"""예매 페이지로 직행하는 링크 생성.

CGV 공식 웹→앱 브리지 페이지를 경유하는 https 링크를 만든다.
모바일에서 탭하면 cgv:// 스킴으로 앱이 열리며(미설치 시 스토어 폴백),
극장(siteNo)·날짜(scnYmd)·영화(movNo, eventYn=Y)가 선택된 예매 화면으로 진입한다.
PC에서는 모바일웹 보기로 폴백된다. (2026-08 라이브 번들 분석 실측)
"""

from __future__ import annotations

from urllib.parse import quote

BRIDGE_URL = "https://cgv.co.kr/met/webAppUsgGoid"


class BookingLinkBuilder:
    def __init__(self, site_no: str, site_name: str = "용산아이파크몰"):
        self._site_no = site_no
        self._site_name = site_name

    def build(self, movie_no: str, date: str) -> str:
        path = (
            f"/cnm/movieBook/cinema?siteNo={self._site_no}&scnYmd={date}"
            f"&movNo={movie_no}&siteNm={quote(self._site_name)}&eventYn=Y"
        )
        return f"{BRIDGE_URL}?device=mobile&r={quote(path, safe='')}"
