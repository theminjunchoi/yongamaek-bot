"""기존 스냅샷과 현재 회차의 diff로 신규 오픈을 감지한다."""

from __future__ import annotations

from ..domain.models import Screening


class OpeningDetector:
    def detect(self, known_keys: set[str], current: list[Screening]) -> list[Screening]:
        """스냅샷에 없는 회차만 반환한다."""
        return [s for s in current if s.key not in known_keys]

    def prune_expired(self, known_keys: set[str], today: str) -> set[str]:
        """상영일이 지난 키를 정리한다. today는 YYYYMMDD."""
        return {k for k in known_keys if k.split("|", 1)[0] >= today}
