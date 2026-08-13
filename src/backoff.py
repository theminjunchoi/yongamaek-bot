"""연속 실패 시 대기시간 계산."""

from __future__ import annotations


class BackoffPolicy:
    def __init__(self, base_sec: float = 120.0, factor: float = 2.0, max_sec: float = 1800.0):
        self._base_sec = base_sec
        self._factor = factor
        self._max_sec = max_sec
        self._failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def record_failure(self) -> float:
        """실패를 기록하고 다음 대기시간(초)을 반환한다."""
        delay = min(self._base_sec * (self._factor**self._failures), self._max_sec)
        self._failures += 1
        return delay

    def reset(self) -> None:
        self._failures = 0
