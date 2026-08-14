"""Discord 웹훅으로 embed 알림을 보내는 Notifier 구현."""

from __future__ import annotations

import logging
from collections import defaultdict

from . import discord_webhook
from .booking_link import BookingLinkBuilder
from .models import Screening
from .notifier import Notifier, NotifyError

logger = logging.getLogger(__name__)

EMBED_COLOR = 0xE71A0F  # CGV 레드
MAX_EMBEDS_PER_MESSAGE = 10


class DiscordWebhookNotifier(Notifier):
    def __init__(
        self,
        webhook_url: str,
        link_builder: BookingLinkBuilder,
        mention: str = "@here",
        timeout_sec: float = 10.0,
    ):
        self._webhook_url = webhook_url
        self._links = link_builder
        self._mention = mention
        self._timeout_sec = timeout_sec

    def notify_openings(self, screenings: list[Screening]) -> None:
        embeds = self._build_embeds(screenings)
        for chunk_start in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
            chunk = embeds[chunk_start : chunk_start + MAX_EMBEDS_PER_MESSAGE]
            content = self._build_content(screenings) if chunk_start == 0 else ""
            self._post({"content": content, "embeds": chunk})

    def _build_content(self, screenings: list[Screening]) -> str:
        """푸시 알림 미리보기에 영화명·날짜가 바로 보이도록 첫 줄을 구성한다."""
        movies = sorted({s.movie_name for s in screenings})
        dates = sorted({s.date for s in screenings})
        date_ko = next(s for s in screenings if s.date == dates[0]).date_display_ko
        date_part = date_ko if len(dates) == 1 else f"{date_ko} 외 {len(dates) - 1}일"
        return f"{self._mention}\n## 🎬 {', '.join(movies)} 용아맥 예매 오픈! — {date_part}"

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
            link = self._links.build(group[0].movie_no, date)
            times = "\n".join(
                f"🕐 **{s.start_time_display}**  ·  잔여 **{s.remaining_seats}**석" for s in group
            )
            embed = {
                "title": product_name,
                "url": link,
                "color": EMBED_COLOR,
                # 제목 필드는 마크다운이 렌더링되지 않으므로 날짜는 본문 헤더(##)로 키운다
                "description": (
                    f"## 📅 {group[0].date_display_ko}\n"
                    f"{times}\n\n👉 **[CGV 앱에서 바로 예매하기]({link})**"
                ),
                "footer": {
                    "text": f"{group[0].screen_name} · {group[0].rating} · 총 {group[0].total_seats}석"
                },
            }
            poster_url = group[0].poster_url
            if poster_url:
                embed["image"] = {"url": poster_url}
            embeds.append(embed)
        return embeds

    def _post(self, payload: dict) -> None:
        discord_webhook.post(self._webhook_url, payload, timeout_sec=self._timeout_sec)
