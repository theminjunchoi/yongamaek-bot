"""영화 → 알림 채널(웹훅) 라우팅 테이블."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import Screening


@dataclass(frozen=True)
class MovieRoute:
    name: str  # 표시용 이름 (예: "오디세이")
    keywords: tuple  # 영화명 매칭 키워드 (한/영 별칭 허용)
    webhook_url: str

    def matches(self, screening: Screening) -> bool:
        text = f"{screening.movie_name} {screening.product_name}".upper()
        return any(k.upper() in text for k in self.keywords)


class RouteTable:
    def __init__(self, routes: list, fallback_webhook_url: str = ""):
        self._routes = routes
        self.fallback_webhook_url = fallback_webhook_url

    @property
    def routes(self) -> list:
        return list(self._routes)

    def match(self, screening: Screening) -> Optional[MovieRoute]:
        """첫 번째로 매칭되는 라우트를 반환한다. 없으면 None."""
        for route in self._routes:
            if route.matches(screening):
                return route
        return None

    @classmethod
    def load(cls, path: Path) -> "RouteTable":
        data = json.loads(path.read_text(encoding="utf-8"))
        routes = [
            MovieRoute(
                name=r["name"],
                keywords=tuple(r.get("keywords") or [r["name"]]),
                webhook_url=r["webhook_url"],
            )
            for r in data.get("routes", [])
        ]
        return cls(routes, fallback_webhook_url=data.get("fallback_webhook_url", ""))
