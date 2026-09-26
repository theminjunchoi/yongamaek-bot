"""폴링 재개 전 스냅샷 기준선을 현재 CGV 상태로 맞춘다. 알림은 절대 보내지 않는다.

중단 기간에 열린 날짜가 재개 첫 사이클에 "신규 오픈"으로 몰려 나가는 것,
오래된 좌석 기준선과 비교해 취소표가 잘못 나가는 것을 막는다.

- snapshot-{siteNo}.json: 기존 키 ∪ 지금 열려 있는 IMAX 영화×날짜 (지난 날짜 정리)
- seats-{siteNo}.json: 비움 → 재개 후 모든 회차가 "최초 관측"이라 기준선만 잡힌다

사용: /opt/homebrew/bin/python3.9 scripts/rebaseline.py (저장소 루트에서, CGV가 막히지 않은 IP로)
"""

from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.domain.config import Config  # noqa: E402
from src.domain.models import KST  # noqa: E402
from src.monitor.detector import OpeningDetector  # noqa: E402
from src.monitor.seat_snapshot_store import JsonSeatSnapshotStore  # noqa: E402
from src.monitor.snapshot_store import JsonSnapshotStore  # noqa: E402
from src.notify.routes import RoutesConfig  # noqa: E402
from src.sources.cgv_http_source import CgvHttpScheduleSource  # noqa: E402
from src.sources.imax_filter import ImaxFilter  # noqa: E402


def main() -> int:
    config = Config.from_env()
    state_dir = config.snapshot_path.parent
    site_nos = [t.site_no for t in RoutesConfig.load(config.routes_path).theaters]
    today = datetime.now(KST).date()
    dates = [(today + timedelta(days=n)).strftime("%Y%m%d") for n in range(config.days_ahead)]

    for site_no in site_nos:
        source = CgvHttpScheduleSource(site_no=site_no)
        current = []
        for i, date in enumerate(dates):
            if i > 0:
                time.sleep(random.uniform(config.request_delay_min_sec, config.request_delay_max_sec))
            # 한 날짜라도 실패하면 기준선이 불완전해지므로 예외를 그대로 올려 중단한다.
            current.extend(ImaxFilter().filter(source.fetch(date)))

        store = JsonSnapshotStore(state_dir / f"snapshot-{site_no}.json")
        before = store.load()
        after = OpeningDetector().prune_expired(before | {s.key for s in current}, today.strftime("%Y%m%d"))
        store.save(after)
        JsonSeatSnapshotStore(state_dir / f"seats-{site_no}.json").save({})

        print(f"[{site_no}] 스냅샷 {len(before)} → {len(after)}키")
        print(f"  추가: {sorted(after - before) or '없음'}")
        print(f"  정리(지난 날짜): {sorted(before - after) or '없음'}")
        print("  좌석 기준선 초기화 (재개 후 최초 관측으로 다시 잡힘)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
