"""Threads data export importer.

Expected structure (ZIP extracted):
  threads_and_replies/posts.json — list of post dicts with 'timestamp' and 'text'
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bot.importers.base import PostRecord


class ThreadsImporter:
    platform = "threads"

    async def detect(self, file_path: Path) -> bool:
        return (file_path / "threads_and_replies" / "posts.json").exists()

    async def parse(self, file_path: Path) -> list[PostRecord]:
        posts_path = file_path / "threads_and_replies" / "posts.json"
        raw = json.loads(posts_path.read_text(encoding="utf-8"))

        records: list[PostRecord] = []
        for entry in raw:
            ts = entry.get("timestamp")
            if ts is None:
                continue
            posted_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            caption = (entry.get("text") or "").strip() or None
            records.append(
                PostRecord(platform=self.platform, posted_at=posted_at, caption=caption)
            )
        return records
