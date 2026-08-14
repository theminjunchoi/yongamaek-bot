"""오픈 패턴 기록: 오픈 감지 이벤트를 채널 한 줄 + JSONL 파일로 남긴다.

채널은 눈으로 보는 타임라인, 파일은 추후 요일·시각 분포 분석용.
기록 실패가 알림 발송을 깨뜨리면 안 되므로 예외를 밖으로 던지지 않는다.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import discord_webhook
from .notifier import NotifyError

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


class OpeningPatternLogger:
    def __init__(self, webhook_url: str, log_path: Path, theater_name: str = ""):
        self._webhook_url = webhook_url
        self._log_path = log_path
        self._theater_name = theater_name

    def record(self, screenings: list) -> None:
        if not screenings:
            return
        detected_at = datetime.now(KST)
        by_movie: dict = defaultdict(list)
        for s in screenings:
            by_movie[s.movie_name].append(s)

        for movie, group in sorted(by_movie.items()):
            dates = sorted({s.date for s in group})
            self._append_jsonl(detected_at, movie, group, dates)
            self._post_line(detected_at, movie, group, dates)

    def _append_jsonl(self, detected_at: datetime, movie: str, group: list, dates: list) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "detected_at": detected_at.isoformat(timespec="seconds"),
                "weekday": "월화수목금토일"[detected_at.weekday()],
                "theater": self._theater_name,
                "movie": movie,
                "movie_no": group[0].movie_no,
                "dates": dates,
                "screening_count": len(group),
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("오픈 패턴 파일 기록 실패: %s", e)

    def _post_line(self, detected_at: datetime, movie: str, group: list, dates: list) -> None:
        first = next(s for s in group if s.date == dates[0])
        date_part = first.date_display_ko if len(dates) == 1 else f"{first.date_display_ko} 외 {len(dates) - 1}일"
        weekday = "월화수목금토일"[detected_at.weekday()]
        theater_tag = f"[{self._theater_name}] " if self._theater_name else ""
        line = (
            f"📖 `{detected_at:%m/%d} ({weekday}) {detected_at:%H:%M}` 감지 — "
            f"{theater_tag}**{movie}** · {date_part} · {len(group)}회차"
        )
        try:
            discord_webhook.post(self._webhook_url, {"content": line})
        except NotifyError as e:
            logger.error("오픈 패턴 채널 기록 실패: %s", e)
