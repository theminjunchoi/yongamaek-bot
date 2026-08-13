"""엔트리포인트: 설정 로드 → 의존성 조립 → 실행."""

from __future__ import annotations

import argparse
import logging
import sys

from typing import Optional

from .app import MonitorApp
from .booking_link import BookingLinkBuilder
from .cgv_http_source import CgvHttpScheduleSource
from .config import Config
from .detector import OpeningDetector
from .discord_notifier import DiscordWebhookNotifier
from .imax_filter import ImaxFilter
from .notifier import ConsoleNotifier, Notifier
from .routes import RouteTable
from .routing_notifier import RoutingNotifier
from .snapshot_store import JsonSnapshotStore


def _build_notifier(config: Config) -> Optional[Notifier]:
    """routes.json이 있으면 영화별 채널 라우팅, 없으면 단일 웹훅 모드."""
    links = BookingLinkBuilder(config.site_no)
    if config.routes_path.exists():
        return RoutingNotifier(RouteTable.load(config.routes_path), links)
    if config.discord_webhook_url:
        return DiscordWebhookNotifier(config.discord_webhook_url, links)
    return None


def build_app(config: Config, notifier: Notifier) -> MonitorApp:
    return MonitorApp(
        source=CgvHttpScheduleSource(site_no=config.site_no),
        imax_filter=ImaxFilter(),
        store=JsonSnapshotStore(config.snapshot_path),
        detector=OpeningDetector(),
        notifier=notifier,
        config=config,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="용아맥(CGV 용산 IMAX) 예매 오픈 알림 봇")
    parser.add_argument("--once", action="store_true", help="1회 조회 후 현재 열린 IMAX 회차를 출력하고 종료")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()

    if args.once:
        app = build_app(config, ConsoleNotifier())
        screenings = app.run_once()
        print(f"\n총 {len(screenings)}개 IMAX 회차가 열려 있습니다.")
        return 0

    notifier = _build_notifier(config)
    if notifier is None:
        print(
            "알림 설정이 없습니다. routes.json(영화별 채널) 또는 .env의 DISCORD_WEBHOOK_URL을 설정하세요.",
            file=sys.stderr,
        )
        return 1

    app = build_app(config, notifier)
    try:
        app.run_forever()
    except KeyboardInterrupt:
        print("종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
