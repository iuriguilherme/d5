"""ImporterRegistry — first-match detection for platform importers."""
from __future__ import annotations

import logging
from pathlib import Path

from bot.importers.base import PlatformImporter, PostRecord

logger = logging.getLogger(__name__)


class ImporterRegistry:
    def __init__(self) -> None:
        self._importers: list[PlatformImporter] = []

    def register(self, importer: PlatformImporter) -> None:
        self._importers.append(importer)

    async def detect_and_parse(self, file_path: Path) -> tuple[str, list[PostRecord]]:
        """Try each registered importer in order; first detect() win parses.

        Returns (platform, records). Raises ValueError if no importer matches.
        """
        for importer in self._importers:
            if await importer.detect(file_path):
                logger.info("importer_matched", platform=importer.platform)
                records = await importer.parse(file_path)
                return importer.platform, records

        raise ValueError(f"No importer matched file: {file_path}")
