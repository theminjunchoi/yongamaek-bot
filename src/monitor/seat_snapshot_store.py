"""회차별 좌석 관측 상태의 영속화.

회차 하나당 두 가지를 기억한다.
- free: 마지막으로 본 잔여석 수 (스케줄 API의 frSeatCnt). 좌석맵을 조회할지
  판단하는 게이트 값.
- honey: 마지막으로 본 "구역 내 예매 가능 좌석" 라벨 집합. 알림 중복 방지용.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class JsonSeatSnapshotStore:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict:
        """{screening_key: {"free": int, "honey": [label, ...]}} 형태로 반환."""
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, state: dict) -> None:
        """임시 파일에 쓰고 원자적으로 교체해 저장 중 손상을 방지한다."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp_path, self._path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def prune_expired(state: dict, today: str) -> dict:
        """상영일이 지난 회차 키를 정리한다. 키 형식은 "YYYYMMDD|관|회차"."""
        return {k: v for k, v in state.items() if k.split("|", 1)[0] >= today}
