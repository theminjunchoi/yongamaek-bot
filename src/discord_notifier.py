"""Discord 웹훅으로 embed 알림을 보내는 Notifier 구현."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections import defaultdict

from .models import Screening
from .notifier import Notifier, NotifyError

logger = logging.getLogger(__name__)

EMBED_COLOR = 0xE71A0F  # CGV 레드
MAX_EMBEDS_PER_MESSAGE = 10


class DiscordWebhookNotifier(Notifier):
    def __init__(self, webhook_url: str, booking_url: str, mention: str = "@here", timeout_sec: float = 10.0):
        self._webhook_url = webhook_url
        self._booking_url = booking_url
        self._mention = mention
        self._timeout_sec = timeout_sec

    def notify_openings(self, screenings: list[Screening]) -> None:
        embeds = self._build_embeds(screenings)
        for chunk_start in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
            chunk = embeds[chunk_start : chunk_start + MAX_EMBEDS_PER_MESSAGE]
            content = f"{self._mention} 🎬 **용아맥 예매 오픈!**" if chunk_start == 0 else ""
            self._post({"content": content, "embeds": chunk})

    def alert(self, message: str) -> None:
        try:
            self._post({"content": f"⚠️ {message}"})
        except NotifyError:
            logger.exception("운영 경고 발송 실패")

    def _build_embeds(self, screenings: list[Screening]) -> list[dict]:
        """같은 영화·날짜의 회차들을 embed 하나로 묶는다."""
        grouped: dict[tuple[str, str], list[Screening]] = defaultdict(list)
        for s in screenings:
            grouped[(s.product_name, s.date)].append(s)

        embeds = []
        for (product_name, date), group in sorted(grouped.items(), key=lambda item: item[0][1]):
            group.sort(key=lambda s: s.start_time)
            times = "\n".join(
                f"• {s.start_time_display} (잔여 {s.remaining_seats}/{s.total_seats}석)" for s in group
            )
            embeds.append(
                {
                    "title": product_name,
                    "url": f"{self._booking_url}&scnYmd={date}",
                    "color": EMBED_COLOR,
                    "description": f"**{group[0].date_display}**\n{times}",
                    "footer": {"text": f"{group[0].screen_name} · {group[0].rating}"},
                }
            )
        return embeds

    def _post(self, payload: dict) -> None:
        request = urllib.request.Request(
            self._webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            # Discord(Cloudflare)가 기본 Python-urllib User-Agent의 POST를 403으로 차단한다
            headers={"Content-Type": "application/json", "User-Agent": "yongamaek-bot/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec):
                pass
        except urllib.error.HTTPError as e:
            raise NotifyError(f"Discord 웹훅 HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise NotifyError(f"Discord 웹훅 네트워크 오류: {e}") from e
