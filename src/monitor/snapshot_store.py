"""알림 완료된 회차 키 집합의 영속화."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class JsonSnapshotStore:
    def __init__(self, path: Path):
        self._path = path

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> set[str]:
        if not self.exists():
            return set()
        with self._path.open(encoding="utf-8") as f:
            return set(json.load(f))

    def save(self, keys: set[str]) -> None:
        """임시 파일에 쓰고 원자적으로 교체해 저장 중 손상을 방지한다."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(keys), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
