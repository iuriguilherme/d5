"""Instagram data export importer.

Expected structure (ZIP extracted):
  content/posts_1.json  — list of post objects with 'timestamp' and 'title'
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bot.importers.base import PostRecord


class InstagramImporter:
    platform = "instagram"

    async def detect(self, file_path: Path) -> bool:
        return (file_path / "content" / "posts_1.json").exists()

    async def parse(self, file_path: Path) -> list[PostRecord]:
        posts_path = file_path / "content" / "posts_1.json"
        raw = json.loads(posts_path.read_text(encoding="utf-8"))

        records: list[PostRecord] = []
        for entry in raw:
            ts = entry.get("timestamp")
            if ts is None:
                continue
            posted_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            # title may be absent or empty
            caption = (entry.get("title") or "").strip() or None
            records.append(
                PostRecord(platform=self.platform, posted_at=posted_at, caption=caption)
            )
        return records
