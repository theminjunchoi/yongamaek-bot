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
from ..domain.seat import YONGSAN_IMAX_HONEY, RowRangeZone, SeatZone


@dataclass(frozen=True)
class MovieRoute:
    name: str  # 표시용 이름 (예: "오디세이")
    keywords: tuple  # 영화명 매칭 키워드 (한/영 별칭 허용)
    webhook_url: str  # 신규 날짜 오픈 알림 채널
    cancel_webhook_url: str = ""  # 명당 취소표 알림 채널. 비우면 이 영화는 취소 감시 안 함

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
    honey_zone: Optional[SeatZone] = None  # 취소표를 볼 좌석 구역. 없으면 기본값(용아맥 명당)

    @property
    def zone(self) -> SeatZone:
        return self.honey_zone or YONGSAN_IMAX_HONEY

    @property
    def watches_cancellations(self) -> bool:
        return any(r.cancel_webhook_url for r in self.routes)

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
                    cancel_webhook_url=r.get("cancel_webhook_url", ""),
                )
                for r in raw
            )

        def make_zone(raw: Optional[dict]) -> Optional[SeatZone]:
            """{"rows": "HIJKL", "min_seat_no": 16, "max_seat_no": 29} 형식(선택)."""
            if not raw:
                return None
            return RowRangeZone.of(
                rows=raw["rows"],
                min_number=int(raw["min_seat_no"]),
                max_number=int(raw["max_seat_no"]),
                label=raw.get("label", "명당"),
            )

        if "theaters" in data:
            theaters = tuple(
                TheaterRoutes(
                    name=t["name"],
                    site_no=t["site_no"],
                    site_name=t.get("site_name", ""),
                    routes=make_routes(t.get("routes", [])),
                    honey_zone=make_zone(t.get("honey_zone")),
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
                    honey_zone=make_zone(data.get("honey_zone")),
                ),
            )

        return cls(
            theaters=theaters,
            alert_webhook_url=data.get("alert_webhook_url", ""),
            pattern_webhook_url=data.get("pattern_webhook_url", ""),
            fallback_webhook_url=data.get("fallback_webhook_url", ""),
        )
