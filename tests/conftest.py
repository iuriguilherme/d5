"""Shared pytest fixtures for the WDWGN test suite."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import Settings


# ── Settings fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Minimal Settings for tests — no .env file required."""
    return Settings(
        telegram_bot_token="0:test-token",
        allowed_user_ids=[12345],
        data_dir=tmp_path,
        log_level="WARNING",
    )


# ── Database fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
async def db_engine(settings: Settings):
    """In-memory async SQLite engine with all models created."""
    from sqlalchemy import event

    import bot.models  # noqa: F401 — registers all models on Base.metadata
    from bot.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async session scoped to a single test, rolled back after."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# ── ChromaDB mock fixture ─────────────────────────────────────────────────────


@pytest.fixture
def mock_vector_store() -> MagicMock:
    """Mock VectorStore — all methods are async-safe MagicMocks."""
    store = MagicMock()
    store.upsert_subject = AsyncMock()
    store.get_subject_embedding = AsyncMock(return_value=[0.0] * 384)
    store.upsert_strategy = AsyncMock()
    store.query_similar_subjects = AsyncMock(return_value=[])
    store.query_strategy_alignment = AsyncMock(return_value=[])
    return store


# ── Telegram bot mock fixture ─────────────────────────────────────────────────


@pytest.fixture
def mock_bot() -> MagicMock:
    """Mock Aiogram Bot instance."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    return bot
