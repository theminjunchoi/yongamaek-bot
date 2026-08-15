"""환경변수(.env 포함) 파싱."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    discord_webhook_url: str
    site_no: str = "0013"  # 용산아이파크몰
    poll_interval_sec: float = 60.0
    # 심야(KST 01~07시) 간격. 예전엔 300초로 늦췄지만, 취소표는 새벽에도 계속
    # 나오므로(실측: 03시대 4분에 2건) 주간과 같은 60초로 둔다. 되돌리려면 이 값만 올리면 된다.
    night_poll_interval_sec: float = 60.0
    days_ahead: int = 14
    frontier_ahead: int = 3  # 매 사이클: 마지막 오픈 날짜 이후 며칠을 볼지
    full_sweep_interval_sec: float = 600.0  # 전체 범위 스캔 주기 (열린 날짜의 새 영화 편성 감지용)
    request_delay_min_sec: float = 1.0
    request_delay_max_sec: float = 2.0
    # 명당 취소표 감시 (대상은 "아직 예매 가능한 회차" = 판매종료 salEndTm 이전)
    seat_sweep_per_cycle: int = 6  # 롤링 스윕: 매 사이클 좌석맵을 갈아볼 회차 수
    seat_max_fetch_per_cycle: int = 25  # 사이클당 좌석맵 조회 상한 (1분 주기 보호)
    seat_request_delay_min_sec: float = 0.3
    seat_request_delay_max_sec: float = 0.6
    snapshot_path: Path = Path("state/snapshot.json")
    routes_path: Path = Path("routes.json")
    alert_after_failures: int = 5
    max_runtime_sec: float = 0.0  # 0이면 무제한. GitHub Actions처럼 잡 시간 제한이 있는 환경용

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> "Config":
        _load_env_file(env_file)
        return cls(
            discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", ""),
            site_no=os.environ.get("CGV_SITE_NO", cls.site_no),
            poll_interval_sec=float(os.environ.get("POLL_INTERVAL_SEC", cls.poll_interval_sec)),
            night_poll_interval_sec=float(
                os.environ.get("NIGHT_POLL_INTERVAL_SEC", cls.night_poll_interval_sec)
            ),
            days_ahead=int(os.environ.get("DAYS_AHEAD", cls.days_ahead)),
            snapshot_path=Path(os.environ.get("SNAPSHOT_PATH", cls.snapshot_path)),
            routes_path=Path(os.environ.get("ROUTES_PATH", cls.routes_path)),
            max_runtime_sec=float(os.environ.get("MAX_RUNTIME_SEC", cls.max_runtime_sec)),
            seat_sweep_per_cycle=int(
                os.environ.get("SEAT_SWEEP_PER_CYCLE", cls.seat_sweep_per_cycle)
            ),
            seat_max_fetch_per_cycle=int(
                os.environ.get("SEAT_MAX_FETCH_PER_CYCLE", cls.seat_max_fetch_per_cycle)
            ),
        )

def _load_env_file(path: Path) -> None:
    """단순 KEY=VALUE 형식의 .env를 읽어 미설정 환경변수만 채운다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
