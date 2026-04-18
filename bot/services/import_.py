"""ImportService — orchestrates file extraction, parsing, and DB insertion."""
from __future__ import annotations

import asyncio
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.importers.registry import ImporterRegistry
from bot.models import ImportBatch, Post
from bot.models.post import PostPlatform, PostSource

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


class ImportService:
    def __init__(
        self,
        registry: ImporterRegistry,
        session_factory: async_sessionmaker[AsyncSession],
        prediction_service,  # PredictionService — circular import avoided by typing as Any
        data_dir: Path,
    ) -> None:
        self._registry = registry
        self._session_factory = session_factory
        self._prediction = prediction_service
        self._data_dir = data_dir

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    async def process(
        self,
        user_id: int,
        batch_id: UUID,
        file_path: Path,
        bot=None,
    ) -> ImportBatch:
        """Extract ZIP (if needed), parse, insert Posts, trigger clustering.

        Returns the created ImportBatch record.
        """
        extract_dir = await asyncio.to_thread(self._extract, file_path, batch_id)

        platform, records = await self._registry.detect_and_parse(extract_dir)

        async with self._session_factory() as session:
            for record in records:
                try:
                    plat = PostPlatform(record.platform)
                except ValueError:
                    plat = PostPlatform.other

                post = Post(
                    user_id=user_id,
                    platform=plat,
                    source=PostSource.imported,
                    posted_at=record.posted_at,
                    caption_excerpt=record.caption,
                )
                session.add(post)

            batch = ImportBatch(
                batch_id=batch_id,
                user_id=user_id,
                platform=platform,
                file_path=str(file_path),
                record_count=len(records),
                imported_at=datetime.now(timezone.utc),
            )
            session.add(batch)
            await session.commit()

        logger.info(
            "import_complete",
            user_id=user_id,
            batch_id=str(batch_id),
            platform=platform,
            count=len(records),
        )

        # Fire clustering in background — non-critical, don't block handler response
        if self._prediction is not None:
            task = asyncio.create_task(
                self._prediction.cluster_import(
                    user_id, batch_id, self._session_factory, bot=bot
                )
            )

            def _on_cluster_done(t: asyncio.Task) -> None:
                if not t.cancelled() and (exc := t.exception()) is not None:
                    logger.error(
                        "cluster_import_failed",
                        user_id=user_id,
                        batch_id=str(batch_id),
                        error=str(exc),
                    )

            task.add_done_callback(_on_cluster_done)

        return batch

    def _extract(self, file_path: Path, batch_id: UUID) -> Path:
        """Synchronous extraction — called via asyncio.to_thread."""
        if not zipfile.is_zipfile(file_path):
            # Already a directory or non-ZIP file — return as-is
            return file_path

        extract_dir = self._data_dir / "imports" / str(batch_id)
        extract_dir.mkdir(parents=True, exist_ok=True)

        safe_root = extract_dir.resolve()
        with zipfile.ZipFile(file_path) as zf:
            for member in zf.namelist():
                member_path = (extract_dir / member).resolve()
                if not member_path.is_relative_to(safe_root):
                    raise ValueError(f"Unsafe ZIP member path: {member!r}")
            zf.extractall(extract_dir)

        return extract_dir


def build_default_registry() -> ImporterRegistry:
    from bot.importers.generic_csv import GenericCsvImporter
    from bot.importers.instagram import InstagramImporter
    from bot.importers.threads import ThreadsImporter
    from bot.importers.tiktok import TikTokImporter

    registry = ImporterRegistry()
    # Platform-specific first; generic CSV last as fallback
    registry.register(InstagramImporter())
    registry.register(TikTokImporter())
    registry.register(ThreadsImporter())
    registry.register(GenericCsvImporter())
    return registry
