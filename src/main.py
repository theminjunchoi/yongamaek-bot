"""엔트리포인트: 설정 로드 → 극장별 의존성 조립 → 실행."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .app import MonitorApp, MonitorCoordinator
from .booking_link import BookingLinkBuilder
from .cgv_http_source import CgvHttpScheduleSource
from .config import Config
from .detector import OpeningDetector
from .discord_notifier import DiscordWebhookNotifier
from .imax_filter import ImaxFilter
from .notifier import ConsoleNotifier
from .pattern_logger import OpeningPatternLogger
from .routes import RoutesConfig, TheaterRoutes
from .routing_notifier import RoutingNotifier
from .snapshot_store import JsonSnapshotStore


def _link_builder(theater: TheaterRoutes) -> BookingLinkBuilder:
    if theater.site_name:
        return BookingLinkBuilder(theater.site_no, theater.site_name)
    return BookingLinkBuilder(theater.site_no)


def _build_monitor(theater: TheaterRoutes, cfg: RoutesConfig, config: Config, notifier) -> MonitorApp:
    state_dir = config.snapshot_path.parent
    pattern_logger = None
    if cfg.pattern_webhook_url:
        pattern_logger = OpeningPatternLogger(
            cfg.pattern_webhook_url, state_dir / "openings.jsonl", theater_name=theater.name
        )
    return MonitorApp(
        source=CgvHttpScheduleSource(site_no=theater.site_no),
        imax_filter=ImaxFilter(),
        store=JsonSnapshotStore(state_dir / f"snapshot-{theater.site_no}.json"),
        detector=OpeningDetector(),
        notifier=notifier,
        config=config,
        pattern_logger=pattern_logger,
        theater_name=theater.name,
    )


def _theaters(config: Config) -> list:
    """routes.json이 있으면 극장 목록을, 없으면 단일 웹훅 모드 극장 하나를 반환한다."""
    if config.routes_path.exists():
        cfg = RoutesConfig.load(config.routes_path)
        monitors = []
        for theater in cfg.theaters:
            notifier = RoutingNotifier(
                theater.routes,
                _link_builder(theater),
                fallback_webhook_url=cfg.fallback_webhook_url,
                alert_webhook_url=cfg.alert_webhook_url,
            )
            monitors.append(_build_monitor(theater, cfg, config, notifier))
        return monitors
    if config.discord_webhook_url:
        theater = TheaterRoutes("용산", config.site_no, "CGV 용산아이파크몰", ())
        notifier = DiscordWebhookNotifier(config.discord_webhook_url, _link_builder(theater))
        return [_build_monitor(theater, RoutesConfig(theaters=()), config, notifier)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="용아맥 알림 봇 (CGV IMAX 예매 오픈 감지)")
    parser.add_argument("--once", action="store_true", help="1회 조회 후 현재 열린 IMAX 회차를 출력하고 종료")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()

    if args.once:
        # 각 극장을 콘솔로 조회 (상태 변경 없음). routes.json이 있으면 극장별로.
        if config.routes_path.exists():
            cfg = RoutesConfig.load(config.routes_path)
            theaters = cfg.theaters
        else:
            theaters = (TheaterRoutes("용산", config.site_no, "CGV 용산아이파크몰", ()),)
        total = 0
        for theater in theaters:
            app = MonitorApp(
                source=CgvHttpScheduleSource(site_no=theater.site_no),
                imax_filter=ImaxFilter(),
                store=JsonSnapshotStore(Path("/dev/null")),
                detector=OpeningDetector(),
                notifier=ConsoleNotifier(),
                config=config,
                theater_name=theater.name,
            )
            print(f"\n=== {theater.name} (siteNo={theater.site_no}) ===")
            screenings = app.run_once()
            total += len(screenings)
        print(f"\n총 {total}개 IMAX 회차가 열려 있습니다.")
        return 0

    monitors = _theaters(config)
    if not monitors:
        print(
            "알림 설정이 없습니다. routes.json(극장·영화별 채널) 또는 .env의 DISCORD_WEBHOOK_URL을 설정하세요.",
            file=sys.stderr,
        )
        return 1

    coordinator = MonitorCoordinator(monitors, max_runtime_sec=config.max_runtime_sec)
    try:
        coordinator.run_forever()
    except KeyboardInterrupt:
        print("종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
