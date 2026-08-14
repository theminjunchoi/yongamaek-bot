"""Discord 웹훅 POST 저수준 헬퍼."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .notifier import NotifyError

USER_AGENT = "yongamaek-bot/1.0"  # Discord(Cloudflare)가 기본 Python UA의 POST를 403으로 차단


def post(webhook_url: str, payload: dict, timeout_sec: float = 10.0) -> None:
    """웹훅으로 payload를 보낸다. 실패 시 NotifyError를 던진다."""
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec):
            pass
    except urllib.error.HTTPError as e:
        raise NotifyError(f"Discord 웹훅 HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise NotifyError(f"Discord 웹훅 네트워크 오류: {e}") from e
