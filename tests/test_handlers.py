"""Tests for Aiogram handlers — start, help, and middleware."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.fsm_storage import SqliteStorage
from bot.main import AllowlistMiddleware
from bot.models import HeuristicProfile, Reminder, User


# ── AllowlistMiddleware ───────────────────────────────────────────────────────


async def test_allowlist_empty_passes_all():
    """Empty ALLOWED_USER_IDS → middleware is disabled, all users pass."""
    mw = AllowlistMiddleware(allowed_user_ids=[])
    handler = AsyncMock(return_value="ok")
    data = {}
    result = await mw(handler, MagicMock(), data)
    assert result == "ok"
    handler.assert_called_once()


async def test_allowlist_blocks_unlisted_user():
    """Unlisted user_id → handler NOT called."""
    mw = AllowlistMiddleware(allowed_user_ids=[111])

    answer_mock = AsyncMock()
    message = MagicMock()
    message.answer = answer_mock

    update = MagicMock()
    update.message = message
    update.message.from_user.id = 999  # not in allowlist
    update.callback_query = None

    handler = AsyncMock(return_value="ok")
    data = {"event_update": update}
    result = await mw(handler, MagicMock(), data)

    assert result is None
    handler.assert_not_called()
    answer_mock.assert_called_once_with("Access denied.")


async def test_allowlist_passes_listed_user():
    """Listed user_id → handler IS called."""
    mw = AllowlistMiddleware(allowed_user_ids=[111])

    update = MagicMock()
    update.message.from_user.id = 111
    update.callback_query = None

    handler = AsyncMock(return_value="ok")
    data = {"event_update": update}
    result = await mw(handler, MagicMock(), data)

    assert result == "ok"
    handler.assert_called_once()


# ── SqliteStorage (FSM) ───────────────────────────────────────────────────────


@pytest.fixture
async def fsm_storage(tmp_path: Path, db_engine):
    """SqliteStorage backed by the in-memory test database — uses tmp_path file."""
    import aiosqlite

    db_path = str(tmp_path / "test_fsm.db")
    # Create fsm_state table in the test DB
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS fsm_state (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                state TEXT,
                data TEXT,
                PRIMARY KEY (user_id, chat_id)
            )"""
        )
        await db.commit()
    return SqliteStorage(db_path=db_path)


KEY = StorageKey(bot_id=1, chat_id=100, user_id=42)


async def test_fsm_set_and_get_state(fsm_storage):
    await fsm_storage.set_state(KEY, "MyState:step1")
    state = await fsm_storage.get_state(KEY)
    assert state == "MyState:step1"


async def test_fsm_get_state_missing(fsm_storage):
    state = await fsm_storage.get_state(KEY)
    assert state is None


async def test_fsm_set_and_get_data(fsm_storage):
    await fsm_storage.set_data(KEY, {"subject_text": "my idea"})
    data = await fsm_storage.get_data(KEY)
    assert data == {"subject_text": "my idea"}


async def test_fsm_get_data_missing(fsm_storage):
    data = await fsm_storage.get_data(KEY)
    assert data == {}


async def test_fsm_state_survives_new_instance(tmp_path):
    """State written by one SqliteStorage instance is readable by another."""
    import aiosqlite

    db_path = str(tmp_path / "fsm_persist.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE fsm_state (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                state TEXT,
                data TEXT,
                PRIMARY KEY (user_id, chat_id)
            )"""
        )
        await db.commit()

    storage1 = SqliteStorage(db_path=db_path)
    await storage1.set_state(KEY, "IdeaStates:waiting_for_text")

    storage2 = SqliteStorage(db_path=db_path)  # new instance, same file
    state = await storage2.get_state(KEY)
    assert state == "IdeaStates:waiting_for_text"


# ── /start handler ────────────────────────────────────────────────────────────


async def test_start_creates_user_and_reminders(db_session: AsyncSession):
    """New user → User record + 4 Reminders + HeuristicProfile created."""
    from bot.handlers.start import cmd_start

    message = MagicMock()
    message.from_user.id = 77777
    message.from_user.username = "testuser"
    message.from_user.first_name = "Test"
    message.answer = AsyncMock()

    await cmd_start(message=message, session=db_session, session_factory=MagicMock())

    user = await db_session.get(User, 77777)
    assert user is not None
    assert user.username == "testuser"

    reminders = (
        await db_session.execute(select(Reminder).where(Reminder.user_id == 77777))
    ).scalars().all()
    assert len(reminders) == 4

    profile = (
        await db_session.execute(
            select(HeuristicProfile).where(HeuristicProfile.user_id == 77777)
        )
    ).scalars().first()
    assert profile is not None


async def test_start_idempotent_for_existing_user(db_session: AsyncSession):
    """/start for existing user does NOT duplicate records."""
    from bot.handlers.start import cmd_start

    user = User(user_id=88888, username="bob")
    db_session.add(user)
    await db_session.flush()

    message = MagicMock()
    message.from_user.id = 88888
    message.from_user.username = "bob"
    message.from_user.first_name = "Bob"
    message.answer = AsyncMock()

    await cmd_start(message=message, session=db_session, session_factory=MagicMock())

    # Should still be just the one user
    users = (
        await db_session.execute(select(User).where(User.user_id == 88888))
    ).scalars().all()
    assert len(users) == 1


async def test_help_contains_all_commands():
    """/help reply contains all command names."""
    from bot.handlers.start import cmd_help, HELP_TEXT

    message = MagicMock()
    message.answer = AsyncMock()

    await cmd_help(message=message)

    message.answer.assert_called_once()
    call_text = message.answer.call_args[0][0]
    for cmd in ["/idea", "/pool", "/pending", "/posted", "/suggest",
                "/schedule", "/import", "/strategy", "/settings", "/help"]:
        assert cmd in call_text, f"Missing {cmd} in help text"
