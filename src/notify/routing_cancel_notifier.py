"""취소표 알림을 영화별 채널로 분배하는 CancellationNotifier 구현.

오픈 알림(RoutingNotifier)과 같은 MovieRoute 매칭을 쓰되, 채널은 라우트의
cancel_webhook_url을 본다. 취소 채널이 없는 영화는 조용히 건너뛴다
(폴백으로 보내면 관심 없는 영화의 취소표가 쏟아진다).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from .booking_link import BookingLinkBuilder
from .cancel_notifier import CancellationNotifier
from .discord_cancel_notifier import DiscordCancellationNotifier
from .notifier import NotifyError

logger = logging.getLogger(__name__)


class RoutingCancellationNotifier(CancellationNotifier):
    def __init__(self, routes: tuple, link_builder: BookingLinkBuilder):
        self._routes = routes
        self._notifiers = {
            route.name: DiscordCancellationNotifier(route.cancel_webhook_url, link_builder)
            for route in routes
            if route.cancel_webhook_url
        }

    @property
    def watches_anything(self) -> bool:
        return bool(self._notifiers)

    def _match(self, screening):
        for route in self._routes:
            if route.matches(screening) and route.name in self._notifiers:
                return route
        return None

    def notify_cancellations(self, cancellations: list) -> None:
        by_route: dict = defaultdict(list)
        for c in cancellations:
            route = self._match(c.screening)
            if route is None:
                logger.debug("취소 채널 없는 영화, 알림 생략: %s", c.screening.movie_name)
                continue
            by_route[route.name].append(c)

        errors = []
        for name, group in by_route.items():
            try:
                self._notifiers[name].notify_cancellations(group)
            except NotifyError as e:
                errors.append(f"{name}: {e}")

        if errors:
            raise NotifyError("; ".join(errors))
