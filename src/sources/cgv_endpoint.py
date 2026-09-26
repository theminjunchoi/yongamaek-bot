"""CGV BFF API 호출 경로 결정: 직접 호출 또는 Cloudflare Worker 중계.

2026-09-17부터 CGV가 GitHub Actions 러너 IP 대역 전체를 403으로 막아,
러너에서는 Worker(`relay/`)를 거쳐 호출한다. 중계 Worker는 경로·쿼리를 그대로
cgv.co.kr로 넘기므로 호출부는 base URL과 토큰 헤더만 바꾸면 된다.

- CGV_RELAY_URL 미설정: 지금까지처럼 cgv.co.kr에 직접 요청
- CGV_RELAY_URL 설정: 해당 Worker로 요청하고 X-Relay-Token 헤더를 붙인다
"""

from __future__ import annotations

import os

DIRECT_BASE = "https://cgv.co.kr"


def api_url(path: str) -> str:
    """`/api/v1/booking/...` 경로를 실제 호출 URL로 바꾼다."""
    base = os.environ.get("CGV_RELAY_URL", "").rstrip("/") or DIRECT_BASE
    return base + path


def relay_headers() -> dict:
    """중계 모드일 때만 Worker 인증 헤더를 돌려준다."""
    if not os.environ.get("CGV_RELAY_URL"):
        return {}
    return {"X-Relay-Token": os.environ.get("CGV_RELAY_TOKEN", "")}
