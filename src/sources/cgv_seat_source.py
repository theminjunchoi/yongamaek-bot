"""CGV 좌석맵 API를 urllib으로 직접 호출하는 SeatSource 구현.

엔드포인트 발견 경위 (2026-08-16, 프런트 번들 역추적 + 실측):
프런트는 `https://api.cgv.co.kr/cnm/atkt/searchIfSeatData`를 부르지만,
클라이언트 fetch 래퍼가 `/cnm/atkt` → `/api/v1/booking` 으로 리라이트하므로
실제 요청은 아래 BFF 경로의 **GET**이다. Authorization 헤더는 accessToken
쿠키가 있을 때만 붙으므로, 무인증 상태에서도 200이 온다.

주의: 스케줄 API와 동일하게 curl/requests가 아닌 urllib이어야 하고
(Cloudflare TLS 핑거프린트 차단), Referer가 없으면 403이다.
응답은 624석 기준 원본 약 540KB이므로 gzip을 반드시 요청한다(약 36KB).
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request

from ..domain.seat import Seat
from .seat_source import SeatFetchError, SeatSource

API_URL = "https://cgv.co.kr/api/v1/booking/searchIfSeatData"
REFERER = "https://cgv.co.kr/cnm/bookMovie/chooseSeatMyself"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


class CgvHttpSeatSource(SeatSource):
    def __init__(self, site_no: str, co_cd: str = "A420", timeout_sec: float = 15.0):
        self._site_no = site_no
        self._co_cd = co_cd
        self._timeout_sec = timeout_sec

    def fetch(self, date: str, screen_no: str, seq: str) -> list[Seat]:
        url = self._build_url(date, screen_no, seq)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": REFERER,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                body = raw.decode("utf-8")
        except urllib.error.HTTPError as e:
            raise SeatFetchError(f"HTTP {e.code} ({date} 회차{seq})", status=e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SeatFetchError(f"네트워크 오류 ({date} 회차{seq}): {e}") from e

        return self._parse(body, date, seq)

    def _build_url(self, date: str, screen_no: str, seq: str) -> str:
        query = urllib.parse.urlencode(
            {
                "coCd": self._co_cd,
                "siteNo": self._site_no,
                "scnYmd": date,
                "scnsNo": screen_no,
                "scnSseq": seq,
            }
        )
        return f"{API_URL}?{query}"

    def _parse(self, body: str, date: str, seq: str) -> list[Seat]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            raise SeatFetchError(f"JSON 파싱 실패 ({date} 회차{seq})") from e

        if payload.get("statusCode") != 0:
            raise SeatFetchError(
                f"API 오류 ({date} 회차{seq}): statusCode={payload.get('statusCode')} "
                f"{payload.get('statusMessage')}"
            )

        data = payload.get("data") or {}
        seats: list[Seat] = []
        # items는 상영관 구획(sbord) 단위 배열. 용아맥 IMAX관은 1개지만 일반화해 전부 훑는다.
        for item in data.get("items") or []:
            for row in item.get("seats") or []:
                seats.append(Seat.from_api(row))

        if not seats:
            raise SeatFetchError(f"좌석 목록이 비어 있음 ({date} 회차{seq})")
        return seats
