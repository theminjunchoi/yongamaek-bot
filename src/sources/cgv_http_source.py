"""CGV BFF API를 urllib으로 직접 호출하는 ScheduleSource 구현.

주의: Cloudflare가 TLS 핑거프린트로 차단하므로 curl/requests가 아닌
표준 라이브러리 urllib을 사용해야 한다 (2026-08 실측).
Referer 헤더가 없으면 403이 반환된다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..domain.models import Screening
from .schedule_source import ScheduleFetchError, ScheduleSource

API_URL = "https://cgv.co.kr/api/v1/booking/searchMovScnInfo"
REFERER = "https://cgv.co.kr/cnm/movieBook/cinema"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


class CgvHttpScheduleSource(ScheduleSource):
    def __init__(self, site_no: str, co_cd: str = "A420", rtctl_scop_cd: str = "08", timeout_sec: float = 15.0):
        self._site_no = site_no
        self._co_cd = co_cd
        self._rtctl_scop_cd = rtctl_scop_cd
        self._timeout_sec = timeout_sec

    def fetch(self, date: str) -> list[Screening]:
        url = self._build_url(date)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": REFERER,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise ScheduleFetchError(f"HTTP {e.code} ({date})", status=e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ScheduleFetchError(f"네트워크 오류 ({date}): {e}") from e

        return self._parse(body, date)

    def _build_url(self, date: str) -> str:
        query = urllib.parse.urlencode(
            {
                "coCd": self._co_cd,
                "siteNo": self._site_no,
                "scnYmd": date,
                "rtctlScopCd": self._rtctl_scop_cd,
            }
        )
        return f"{API_URL}?{query}"

    def _parse(self, body: str, date: str) -> list[Screening]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            raise ScheduleFetchError(f"JSON 파싱 실패 ({date})") from e

        if payload.get("statusCode") != 0:
            raise ScheduleFetchError(
                f"API 오류 ({date}): statusCode={payload.get('statusCode')} {payload.get('statusMessage')}"
            )

        rows = payload.get("data") or []  # 예매 미오픈 날짜는 data가 null/빈 배열
        return [Screening.from_api(row) for row in rows]
