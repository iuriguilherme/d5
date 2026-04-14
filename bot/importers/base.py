"""Base types for platform importers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass
class PostRecord:
    platform: str
    posted_at: datetime
    caption: str | None = None


class PlatformImporter(Protocol):
    platform: str

    async def detect(self, file_path: Path) -> bool:
        """Return True if this importer can handle the given file/directory."""
        ...

    async def parse(self, file_path: Path) -> list[PostRecord]:
        """Parse file/directory and return a list of PostRecords."""
        ...
