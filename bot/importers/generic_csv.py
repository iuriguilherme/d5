"""Generic CSV importer — works with any CSV that has date and caption columns.

Default column names: 'date', 'caption'. Configurable via constructor.
Date parsed with dateutil.parser for maximum flexibility.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from bot.importers.base import PostRecord


class GenericCsvImporter:
    platform = "other"

    def __init__(
        self,
        date_col: str = "date",
        caption_col: str = "caption",
        platform: str = "other",
    ) -> None:
        self._date_col = date_col
        self._caption_col = caption_col
        self.platform = platform

    async def detect(self, file_path: Path) -> bool:
        """Match any .csv file directly, or a directory containing exactly one .csv."""
        if file_path.suffix.lower() == ".csv":
            return True
        csv_files = list(file_path.glob("*.csv")) if file_path.is_dir() else []
        return len(csv_files) == 1

    async def parse(self, file_path: Path) -> list[PostRecord]:
        if file_path.is_dir():
            csv_files = list(file_path.glob("*.csv"))
            if not csv_files:
                return []
            file_path = csv_files[0]

        from dateutil import parser as dateutil_parser  # type: ignore[import]

        records: list[PostRecord] = []
        with file_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_val = row.get(self._date_col, "").strip()
                if not date_val:
                    continue
                try:
                    posted_at = dateutil_parser.parse(date_val)
                    if posted_at.tzinfo is None:
                        posted_at = posted_at.replace(tzinfo=timezone.utc)
                except (ValueError, OverflowError):
                    continue
                caption = (row.get(self._caption_col) or "").strip() or None
                records.append(
                    PostRecord(platform=self.platform, posted_at=posted_at, caption=caption)
                )
        return records
