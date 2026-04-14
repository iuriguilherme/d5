"""TikTok data export importer.

Expected structure (ZIP extracted):
  user_data.json — nested: Activity.Video Browsing History.VideoList[].Date
  OR: Video.Videos.VideoList[].Date, Link
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bot.importers.base import PostRecord

# TikTok exports dates as "YYYY-MM-DD HH:MM:SS" or ISO-like strings
_DATE_FMTS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
]


def _parse_date(value: str) -> datetime | None:
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class TikTokImporter:
    platform = "tiktok"

    async def detect(self, file_path: Path) -> bool:
        return (file_path / "user_data.json").exists()

    async def parse(self, file_path: Path) -> list[PostRecord]:
        raw = json.loads((file_path / "user_data.json").read_text(encoding="utf-8"))

        # Navigate to the video list — structure varies by export version
        video_list: list[dict] = []
        try:
            video_list = raw["Video"]["Videos"]["VideoList"]
        except (KeyError, TypeError):
            pass

        if not video_list:
            try:
                video_list = raw["Activity"]["Video Browsing History"]["VideoList"]
            except (KeyError, TypeError):
                pass

        records: list[PostRecord] = []
        for entry in video_list:
            date_str = entry.get("Date") or entry.get("date")
            if not date_str:
                continue
            posted_at = _parse_date(str(date_str))
            if posted_at is None:
                continue
            caption = (entry.get("Link") or entry.get("link") or "").strip() or None
            records.append(
                PostRecord(platform=self.platform, posted_at=posted_at, caption=caption)
            )
        return records
