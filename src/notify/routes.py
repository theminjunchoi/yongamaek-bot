"""영화 → 알림 채널(웹훅) 라우팅 설정.

극장(TheaterRoutes)마다 자기 영화별 라우트를 갖고, 최상위 RoutesConfig가
극장 목록과 공용 웹훅(장애·오픈패턴·폴백)을 보관한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..domain.models import Screening


@dataclass(frozen=True)
class MovieRoute:
    name: str  # 표시용 이름 (예: "오디세이")
    keywords: tuple  # 영화명 매칭 키워드 (한/영 별칭 허용)
    webhook_url: str

    def matches(self, screening: Screening) -> bool:
        text = f"{screening.movie_name} {screening.product_name}".upper()
        return any(k.upper() in text for k in self.keywords)


@dataclass(frozen=True)
class TheaterRoutes:
    """극장 하나의 감시 대상과 영화별 라우트."""

    name: str  # 표시용 (예: "용산")
    site_no: str  # CGV 극장 코드 (예: "0013")
    site_name: str  # 예매 딥링크용 (예: "CGV 용산아이파크몰")
    routes: tuple  # (MovieRoute, ...)

    def match(self, screening: Screening) -> Optional[MovieRoute]:
        for route in self.routes:
            if route.matches(screening):
                return route
        return None


@dataclass(frozen=True)
class RoutesConfig:
    theaters: tuple  # (TheaterRoutes, ...)
    alert_webhook_url: str = ""  # 봇 장애 경고 (공용)
    pattern_webhook_url: str = ""  # 오픈 패턴 기록 (공용)
    fallback_webhook_url: str = ""  # 라우트 없는 새 영화 (공용)

    @classmethod
    def load(cls, path: Path) -> "RoutesConfig":
        data = json.loads(path.read_text(encoding="utf-8"))

        def make_routes(raw: list) -> tuple:
            return tuple(
                MovieRoute(
                    name=r["name"],
                    keywords=tuple(r.get("keywords") or [r["name"]]),
                    webhook_url=r["webhook_url"],
                )
                for r in raw
            )

        if "theaters" in data:
            theaters = tuple(
                TheaterRoutes(
                    name=t["name"],
                    site_no=t["site_no"],
                    site_name=t.get("site_name", ""),
                    routes=make_routes(t.get("routes", [])),
                )
                for t in data["theaters"]
            )
        else:
            # 하위호환: 단일 극장(용산) 형식
            theaters = (
                TheaterRoutes(
                    name=data.get("name", "용산"),
                    site_no=data.get("site_no", "0013"),
                    site_name=data.get("site_name", "CGV 용산아이파크몰"),
                    routes=make_routes(data.get("routes", [])),
                ),
            )

        return cls(
            theaters=theaters,
            alert_webhook_url=data.get("alert_webhook_url", ""),
            pattern_webhook_url=data.get("pattern_webhook_url", ""),
            fallback_webhook_url=data.get("fallback_webhook_url", ""),
        )
