"""영화별 채널로 알림을 분배하는 Notifier 구현.

사용자는 Discord에서 보고 싶은 영화 채널의 알림만 켜두면 된다.
라우트에 없는 영화는 폴백 채널로 보내 새 영화 오픈을 놓치지 않게 한다.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from .booking_link import BookingLinkBuilder
from .discord_notifier import DiscordWebhookNotifier
from .notifier import Notifier, NotifyError

logger = logging.getLogger(__name__)


class RoutingNotifier(Notifier):
    def __init__(
        self,
        routes: tuple,
        link_builder: BookingLinkBuilder,
        fallback_webhook_url: str = "",
        alert_webhook_url: str = "",
    ):
        self._routes = routes
        self._notifiers = {
            route.name: DiscordWebhookNotifier(route.webhook_url, link_builder)
            for route in routes
        }
        self._fallback: Optional[DiscordWebhookNotifier] = (
            DiscordWebhookNotifier(fallback_webhook_url, link_builder)
            if fallback_webhook_url
            else None
        )
        self._alert: Optional[DiscordWebhookNotifier] = (
            DiscordWebhookNotifier(alert_webhook_url, link_builder)
            if alert_webhook_url
            else None
        )

    def _match(self, screening):
        for route in self._routes:
            if route.matches(screening):
                return route
        return None

    def notify_openings(self, screenings: list) -> None:
        by_route: dict = defaultdict(list)
        unmatched: list = []
        for s in screenings:
            route = self._match(s)
            if route is not None:
                by_route[route.name].append(s)
            else:
                unmatched.append(s)

        errors = []
        for name, group in by_route.items():
            try:
                self._notifiers[name].notify_openings(group)
            except NotifyError as e:
                errors.append(f"{name}: {e}")

        if unmatched:
            self._notify_unmatched(unmatched, errors)

        if errors:
            # 하나라도 실패하면 사이클 실패로 처리해 다음 사이클에 재시도한다.
            # (성공한 채널은 재시도 시 중복 알림이 갈 수 있으나 드물고 무해하다)
            raise NotifyError("; ".join(errors))

    def alert(self, message: str) -> None:
        target = self._alert or self._fallback or next(iter(self._notifiers.values()), None)
        if target is None:
            logger.warning("경고를 보낼 채널이 없습니다: %s", message)
            return
        target.alert(message)

    def _notify_unmatched(self, screenings: list, errors: list) -> None:
        names = sorted({s.movie_name for s in screenings})
        if self._fallback is None:
            logger.info("라우트 없는 영화 오픈 감지(알림 생략): %s", ", ".join(names))
            return
        try:
            self._fallback.notify_openings(screenings)
        except NotifyError as e:
            errors.append(f"폴백: {e}")
