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
    night_poll_interval_sec: float = 300.0  # KST 01~07시
    days_ahead: int = 14
    request_delay_min_sec: float = 1.0
    request_delay_max_sec: float = 2.0
    snapshot_path: Path = Path("state/snapshot.json")
    alert_after_failures: int = 5

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
        )

    @property
    def booking_url(self) -> str:
        return f"https://cgv.co.kr/cnm/movieBook/cinema?siteNo={self.site_no}"


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
