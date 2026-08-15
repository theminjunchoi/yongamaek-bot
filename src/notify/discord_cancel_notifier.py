"""Discord 웹훅으로 취소표 알림을 보내는 CancellationNotifier 구현.

취소표는 오픈 알림과 성격이 다르다. 몇 초 안에 선점당할 수 있으므로
"어느 자리인지"와 "연석인지"가 한눈에 보여야 하고, 포스터처럼 큰 이미지로
스크롤을 잡아먹으면 오히려 방해가 된다. 그래서 embed를 작게 유지한다.
"""

from __future__ import annotations

import logging

from . import discord_webhook
from .booking_link import BookingLinkBuilder
from .cancel_notifier import CancellationNotifier
from .notifier import NotifyError

logger = logging.getLogger(__name__)

EMBED_COLOR = 0x2ECC71  # 초록 — CGV 레드(오픈 알림)와 구분
MAX_EMBEDS_PER_MESSAGE = 10


class DiscordCancellationNotifier(CancellationNotifier):
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

    def notify_cancellations(self, cancellations: list) -> None:
        if not cancellations:
            return
        embeds = [self._build_embed(c) for c in cancellations]
        for start in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
            chunk = embeds[start : start + MAX_EMBEDS_PER_MESSAGE]
            content = self._build_content(cancellations) if start == 0 else ""
            discord_webhook.post(
                self._webhook_url,
                {"content": content, "embeds": chunk},
                timeout_sec=self._timeout_sec,
            )

    def _build_content(self, cancellations: list) -> str:
        """푸시 미리보기 한 줄. 영화와 좌석이 알림창에서 바로 보여야 한다."""
        first = cancellations[0]
        head = f"{self._mention}\n## 🎟️ {first.screening.movie_name} {first.zone_label} 취소표"
        if len(cancellations) == 1:
            return f"{head} — {first.seat_headline}"
        return f"{head} — {len(cancellations)}개 회차"

    def _build_embed(self, cancellation) -> dict:
        """회차 카드 하나. 제목=언제, 필드=자리·마감·잔여 순으로 훑어 읽게 한다."""
        s = cancellation.screening
        link = self._links.build(s.movie_no, s.date)

        seat_value = f"**{cancellation.seat_summary}**"
        if cancellation.run_detail:
            seat_value += f"\n{cancellation.run_detail}"

        return {
            "title": f"📅 {s.date_display_ko} {s.start_time_display}",
            "url": link,
            "color": EMBED_COLOR,
            "description": f"🎬 **{s.movie_name}** · {s.screen_name}",
            "fields": [
                {"name": f"💺 {cancellation.zone_label} 좌석", "value": seat_value, "inline": True},
                {"name": "⏳ 예매 마감", "value": self._sale_end_display(s), "inline": True},
                {"name": "🎫 회차 잔여", "value": f"{s.remaining_seats}석", "inline": True},
                {"name": "​", "value": f"### 👉 [CGV 앱에서 바로 예매하기]({link})"},
            ],
            "footer": {"text": "취소표는 몇 초 만에 사라질 수 있습니다"},
        }

    @staticmethod
    def _sale_end_display(screening) -> str:
        """"2115" -> "21:15". 값이 없으면 상영 시작 시각으로 대체."""
        t = (screening.sale_end_time or screening.start_time).zfill(4)
        return f"{t[:2]}:{t[2:]}"

    def alert(self, message: str) -> None:
        """운영 경고. 실패해도 예외를 밖으로 던지지 않는다."""
        try:
            discord_webhook.post(
                self._webhook_url, {"content": f"⚠️ {message}"}, timeout_sec=self._timeout_sec
            )
        except NotifyError:
            logger.exception("취소 알림 채널 경고 발송 실패")
