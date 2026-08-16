"""엔트리포인트: 설정 로드 → 극장별 의존성 조립 → 실행."""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path

from .domain.config import Config
from .monitor.app import MonitorApp, MonitorCoordinator
from .monitor.cancel_detector import CancellationDetector
from .monitor.cancel_watcher import CancelWatcher
from .monitor.detector import OpeningDetector
from .monitor.seat_snapshot_store import JsonSeatSnapshotStore
from .monitor.snapshot_store import JsonSnapshotStore
from .notify.booking_link import BookingLinkBuilder
from .notify.discord_notifier import DiscordWebhookNotifier
from .notify.notifier import ConsoleNotifier
from .notify.pattern_logger import OpeningPatternLogger
from .notify.routes import RoutesConfig, TheaterRoutes
from .notify.routing_cancel_notifier import RoutingCancellationNotifier
from .notify.routing_notifier import RoutingNotifier
from .sources.cgv_http_source import CgvHttpScheduleSource
from .sources.cgv_seat_source import CgvHttpSeatSource
from .sources.imax_filter import ImaxFilter


def _link_builder(theater: TheaterRoutes) -> BookingLinkBuilder:
    if theater.site_name:
        return BookingLinkBuilder(theater.site_no, theater.site_name)
    return BookingLinkBuilder(theater.site_no)


def _build_cancel_watcher(
    theater: TheaterRoutes, config: Config, state_dir: Path, alert
) -> CancelWatcher:
    """명당 취소표 감시자. 취소 채널이 하나도 없는 극장은 만들지 않는다."""
    return CancelWatcher(
        seat_source=CgvHttpSeatSource(site_no=theater.site_no),
        zone=theater.zone,
        store=JsonSeatSnapshotStore(state_dir / f"seats-{theater.site_no}.json"),
        detector=CancellationDetector(),
        notifier=RoutingCancellationNotifier(theater.routes, _link_builder(theater)),
        sweep_per_cycle=config.seat_sweep_per_cycle,
        max_fetch_per_cycle=config.seat_max_fetch_per_cycle,
        request_delay_min_sec=config.seat_request_delay_min_sec,
        request_delay_max_sec=config.seat_request_delay_max_sec,
        alert_after_failures=config.alert_after_failures,
        alert=alert,
        theater_name=theater.name,
    )


def _build_monitor(theater: TheaterRoutes, cfg: RoutesConfig, config: Config, notifier) -> MonitorApp:
    state_dir = config.snapshot_path.parent
    pattern_logger = None
    if cfg.pattern_webhook_url:
        pattern_logger = OpeningPatternLogger(
            cfg.pattern_webhook_url, state_dir / "openings.jsonl", theater_name=theater.name
        )
    cancel_watcher = None
    if theater.watches_cancellations:
        cancel_watcher = _build_cancel_watcher(theater, config, state_dir, notifier.alert)
    return MonitorApp(
        source=CgvHttpScheduleSource(site_no=theater.site_no),
        imax_filter=ImaxFilter(),
        store=JsonSnapshotStore(state_dir / f"snapshot-{theater.site_no}.json"),
        detector=OpeningDetector(),
        notifier=notifier,
        config=config,
        pattern_logger=pattern_logger,
        cancel_watcher=cancel_watcher,
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


def _print_seat_status(theater: TheaterRoutes, screenings: list, config: Config) -> None:
    """회차별 명당 좌석 현황을 출력한다 (진단용, 회차당 좌석맵 1요청)."""
    from datetime import datetime

    from .domain.models import KST
    from .domain.seat import format_runs
    from .sources.seat_source import SeatFetchError

    source = CgvHttpSeatSource(site_no=theater.site_no)
    detector = CancellationDetector()
    zone = theater.zone
    now = datetime.now(KST)
    print(f"\n--- {zone.label} 구역 현황 (아직 상영 시작 전인 회차) ---")
    for s in sorted(screenings, key=lambda s: (s.date, s.start_time)):
        if not s.is_before_start(now):
            continue
        try:
            seats = source.fetch(s.date, s.screen_no, s.seq)
        except SeatFetchError as e:
            print(f"  {s.date_display} {s.start_time_display} 조회 실패: {e}")
            continue
        available = detector.available_in_zone(seats, zone)
        detail = format_runs(available) if available else "없음"
        print(
            f"  {s.date_display} {s.start_time_display} {s.movie_name} "
            f"| 회차 잔여 {s.remaining_seats:>3}석 | {zone.label} {len(available):>2}석  {detail}"
        )
        time.sleep(random.uniform(config.seat_request_delay_min_sec, config.seat_request_delay_max_sec))


def main() -> int:
    parser = argparse.ArgumentParser(description="용아맥 알림 봇 (CGV IMAX 예매 오픈 감지)")
    parser.add_argument("--once", action="store_true", help="1회 조회 후 현재 열린 IMAX 회차를 출력하고 종료")
    parser.add_argument(
        "--seats",
        action="store_true",
        help="--once와 함께: 회차별 명당 좌석 현황도 조회해 출력 (회차당 1요청)",
    )
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
            if args.seats:
                _print_seat_status(theater, screenings, config)
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
