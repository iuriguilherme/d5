"""Tests for platform importers and ImportService."""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.importers.base import PostRecord
from bot.importers.registry import ImporterRegistry


# ── Fixtures: write fake export files ─────────────────────────────────────────


@pytest.fixture
def instagram_dir(tmp_path: Path) -> Path:
    """Instagram export directory with content/posts_1.json."""
    content_dir = tmp_path / "instagram_export" / "content"
    content_dir.mkdir(parents=True)
    posts = [
        {"timestamp": 1700000000, "title": "My first post"},
        {"timestamp": 1700100000, "title": ""},
        {"timestamp": 1700200000},  # no title
    ]
    (content_dir / "posts_1.json").write_text(json.dumps(posts), encoding="utf-8")
    return tmp_path / "instagram_export"


@pytest.fixture
def instagram_zip(tmp_path: Path, instagram_dir: Path) -> Path:
    """ZIP of the instagram export directory."""
    zip_path = tmp_path / "instagram.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in instagram_dir.rglob("*"):
            zf.write(f, f.relative_to(instagram_dir))
    return zip_path


@pytest.fixture
def tiktok_dir(tmp_path: Path) -> Path:
    """TikTok export directory with user_data.json."""
    export_dir = tmp_path / "tiktok_export"
    export_dir.mkdir()
    data = {
        "Video": {
            "Videos": {
                "VideoList": [
                    {"Date": "2023-11-14 12:00:00", "Link": "https://tiktok.com/v1"},
                    {"Date": "2023-11-15 18:30:00", "Link": ""},
                ]
            }
        }
    }
    (export_dir / "user_data.json").write_text(json.dumps(data), encoding="utf-8")
    return export_dir


@pytest.fixture
def threads_dir(tmp_path: Path) -> Path:
    """Threads export directory."""
    export_dir = tmp_path / "threads_export"
    posts_dir = export_dir / "threads_and_replies"
    posts_dir.mkdir(parents=True)
    posts = [
        {"timestamp": 1700000000, "text": "Hello Threads"},
        {"timestamp": 1700100000, "text": ""},
    ]
    (posts_dir / "posts.json").write_text(json.dumps(posts), encoding="utf-8")
    return export_dir


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    """Generic CSV export file."""
    csv_path = tmp_path / "posts.csv"
    csv_path.write_text(
        "date,caption\n"
        "2023-11-14 12:00:00,My caption\n"
        "2023-11-15 18:30:00,\n"
        "not-a-date,Should be skipped\n",
        encoding="utf-8",
    )
    return csv_path


# ── InstagramImporter ─────────────────────────────────────────────────────────


async def test_instagram_detect_true(instagram_dir: Path):
    from bot.importers.instagram import InstagramImporter
    assert await InstagramImporter().detect(instagram_dir) is True


async def test_instagram_detect_false(tmp_path: Path):
    from bot.importers.instagram import InstagramImporter
    assert await InstagramImporter().detect(tmp_path) is False


async def test_instagram_parse_records(instagram_dir: Path):
    from bot.importers.instagram import InstagramImporter
    records = await InstagramImporter().parse(instagram_dir)
    assert len(records) == 3
    assert records[0].platform == "instagram"
    assert records[0].caption == "My first post"
    assert records[1].caption is None  # empty title
    assert records[2].caption is None  # missing title


async def test_instagram_parse_timestamps(instagram_dir: Path):
    from bot.importers.instagram import InstagramImporter
    records = await InstagramImporter().parse(instagram_dir)
    assert records[0].posted_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)


# ── TikTokImporter ────────────────────────────────────────────────────────────


async def test_tiktok_detect_true(tiktok_dir: Path):
    from bot.importers.tiktok import TikTokImporter
    assert await TikTokImporter().detect(tiktok_dir) is True


async def test_tiktok_detect_false(tmp_path: Path):
    from bot.importers.tiktok import TikTokImporter
    assert await TikTokImporter().detect(tmp_path) is False


async def test_tiktok_parse_records(tiktok_dir: Path):
    from bot.importers.tiktok import TikTokImporter
    records = await TikTokImporter().parse(tiktok_dir)
    assert len(records) == 2
    assert records[0].platform == "tiktok"
    assert records[0].caption == "https://tiktok.com/v1"
    assert records[1].caption is None  # empty link


async def test_tiktok_parse_timestamps(tiktok_dir: Path):
    from bot.importers.tiktok import TikTokImporter
    records = await TikTokImporter().parse(tiktok_dir)
    assert records[0].posted_at == datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


# ── ThreadsImporter ───────────────────────────────────────────────────────────


async def test_threads_detect_true(threads_dir: Path):
    from bot.importers.threads import ThreadsImporter
    assert await ThreadsImporter().detect(threads_dir) is True


async def test_threads_detect_false(tmp_path: Path):
    from bot.importers.threads import ThreadsImporter
    assert await ThreadsImporter().detect(tmp_path) is False


async def test_threads_parse_records(threads_dir: Path):
    from bot.importers.threads import ThreadsImporter
    records = await ThreadsImporter().parse(threads_dir)
    assert len(records) == 2
    assert records[0].platform == "threads"
    assert records[0].caption == "Hello Threads"
    assert records[1].caption is None


# ── GenericCsvImporter ────────────────────────────────────────────────────────


async def test_csv_detect_csv_file(csv_file: Path):
    from bot.importers.generic_csv import GenericCsvImporter
    assert await GenericCsvImporter().detect(csv_file) is True


async def test_csv_detect_directory_with_one_csv(tmp_path: Path, csv_file: Path):
    from bot.importers.generic_csv import GenericCsvImporter
    # csv_file is in tmp_path — detect on the directory
    assert await GenericCsvImporter().detect(tmp_path) is True


async def test_csv_detect_false_empty_dir(tmp_path: Path):
    from bot.importers.generic_csv import GenericCsvImporter
    empty = tmp_path / "empty"
    empty.mkdir()
    assert await GenericCsvImporter().detect(empty) is False


async def test_csv_parse_records(csv_file: Path):
    from bot.importers.generic_csv import GenericCsvImporter
    records = await GenericCsvImporter().parse(csv_file)
    # 3 rows: 2 valid, 1 bad date skipped
    assert len(records) == 2
    assert records[0].caption == "My caption"
    assert records[1].caption is None


async def test_csv_custom_columns(tmp_path: Path):
    from bot.importers.generic_csv import GenericCsvImporter
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("when,text\n2023-01-01,hello\n", encoding="utf-8")
    importer = GenericCsvImporter(date_col="when", caption_col="text")
    records = await importer.parse(csv_path)
    assert len(records) == 1
    assert records[0].caption == "hello"


# ── ImporterRegistry ──────────────────────────────────────────────────────────


async def test_registry_first_match_wins(instagram_dir: Path, tmp_path: Path):
    from bot.importers.instagram import InstagramImporter
    from bot.importers.tiktok import TikTokImporter

    registry = ImporterRegistry()
    registry.register(InstagramImporter())
    registry.register(TikTokImporter())

    platform, records = await registry.detect_and_parse(instagram_dir)
    assert platform == "instagram"


async def test_registry_no_match_raises(tmp_path: Path):
    registry = ImporterRegistry()
    empty_dir = tmp_path / "nothing"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="No importer matched"):
        await registry.detect_and_parse(empty_dir)


# ── ImportService integration ─────────────────────────────────────────────────


async def test_import_service_creates_posts_and_batch(
    db_session: AsyncSession,
    instagram_dir: Path,
    tmp_path: Path,
):
    from bot.models import ImportBatch, Post, User
    from bot.importers.instagram import InstagramImporter
    from bot.services.import_ import ImportService

    user_id = 90001
    db_session.add(User(user_id=user_id))
    await db_session.flush()

    registry = ImporterRegistry()
    registry.register(InstagramImporter())

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)

    svc = ImportService(
        registry=registry,
        session_factory=mock_factory,
        prediction_service=None,
        data_dir=tmp_path,
    )

    batch_id = uuid4()
    # Pass the directory directly (no ZIP needed — _extract returns it as-is)
    batch = await svc.process(user_id=user_id, batch_id=batch_id, file_path=instagram_dir)

    assert batch.record_count == 3
    assert batch.platform == "instagram"

    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 3


async def test_import_service_handles_zip(
    db_session: AsyncSession,
    instagram_zip: Path,
    tmp_path: Path,
):
    from bot.models import ImportBatch, Post, User
    from bot.importers.instagram import InstagramImporter
    from bot.services.import_ import ImportService

    user_id = 90002
    db_session.add(User(user_id=user_id))
    await db_session.flush()

    registry = ImporterRegistry()
    registry.register(InstagramImporter())

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)

    svc = ImportService(
        registry=registry,
        session_factory=mock_factory,
        prediction_service=None,
        data_dir=tmp_path,
    )

    batch_id = uuid4()
    batch = await svc.process(user_id=user_id, batch_id=batch_id, file_path=instagram_zip)

    assert batch.record_count == 3
    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 3
