"""예매 페이지로 직행하는 링크 생성.

CGV 공식 웹→앱 브리지 페이지를 경유하는 https 링크를 만든다.
모바일에서 탭하면 cgv:// 스킴으로 앱이 열리며(미설치 시 스토어 폴백),
영화·날짜·극장이 선택된 예매 화면으로 진입한다. PC에서는 모바일웹으로 폴백.

주의 (2026-08 라이브 번들 분석 실측):
- 반드시 "영화별 예매"(/cnm/movieBook/movie) 경로여야 한다. 극장별 예매(cinema)
  경로는 딥링크 파라미터를 받으면 /movie로 강제 이동하며 주입 상태를 초기화한다.
- eventYn=Y와 movNo·scnYmd·siteNo·siteNm 4개가 전부 있어야 주입 분기가 성립한다.
"""

from __future__ import annotations

from urllib.parse import quote

BRIDGE_URL = "https://cgv.co.kr/met/webAppUsgGoid"


class BookingLinkBuilder:
    def __init__(self, site_no: str, site_name: str = "CGV 용산아이파크몰"):
        self._site_no = site_no
        self._site_name = site_name

    def build(self, movie_no: str, date: str) -> str:
        path = (
            f"/cnm/movieBook/movie?movNo={movie_no}&scnYmd={date}"
            f"&siteNo={self._site_no}&siteNm={quote(self._site_name)}&eventYn=Y"
        )
        return f"{BRIDGE_URL}?device=mobile&r={quote(path, safe='')}"
