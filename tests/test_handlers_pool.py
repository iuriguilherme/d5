"""Tests for /pool and /pending handlers."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Subject, User
from bot.models.subject import SubjectSource, SubjectStatus


async def _seed_user(session: AsyncSession, user_id: int) -> User:
    user = User(user_id=user_id)
    session.add(user)
    await session.flush()
    return user


def _make_message(user_id: int = 1) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 1) -> MagicMock:
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.chat.id = user_id
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _subject(user_id: int, text: str, status: SubjectStatus = SubjectStatus.active) -> Subject:
    return Subject(
        user_id=user_id,
        text=text,
        source=SubjectSource.manual,
        status=status,
    )


# ── /pool (empty) ─────────────────────────────────────────────────────────────


async def test_pool_empty(db_session: AsyncSession):
    from bot.handlers.pool import cmd_pool

    await _seed_user(db_session, 60001)
    message = _make_message(user_id=60001)
    await cmd_pool(message=message, session=db_session)

    message.answer.assert_called_once()
    assert "empty" in message.answer.call_args[0][0].lower()


# ── /pool (with subjects) ─────────────────────────────────────────────────────


async def test_pool_shows_subjects(db_session: AsyncSession):
    from bot.handlers.pool import cmd_pool

    user_id = 60002
    await _seed_user(db_session, user_id)
    for i in range(3):
        db_session.add(_subject(user_id, f"Subject {i}"))
    await db_session.commit()

    message = _make_message(user_id=user_id)
    await cmd_pool(message=message, session=db_session)

    message.answer.assert_called_once()
    text = message.answer.call_args[1].get("text") or message.answer.call_args[0][0]
    assert "Subject 0" in text or "3 total" in text


async def test_pool_shows_count(db_session: AsyncSession):
    from bot.handlers.pool import cmd_pool

    user_id = 60003
    await _seed_user(db_session, user_id)
    for i in range(7):
        db_session.add(_subject(user_id, f"Idea {i}"))
    await db_session.commit()

    message = _make_message(user_id=user_id)
    await cmd_pool(message=message, session=db_session)

    message.answer.assert_called_once()
    call_kwargs = message.answer.call_args
    text = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("text", "")
    assert "7 total" in text


# ── pool pagination ───────────────────────────────────────────────────────────


async def test_pool_page_callback(db_session: AsyncSession):
    from bot.handlers.pool import pool_page

    user_id = 60004
    await _seed_user(db_session, user_id)
    for i in range(7):
        db_session.add(_subject(user_id, f"Paged Idea {i}"))
    await db_session.commit()

    callback = _make_callback(data="pool:page:1", user_id=user_id)
    await pool_page(callback=callback, session=db_session)

    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── /pending (empty) ──────────────────────────────────────────────────────────


async def test_pending_empty(db_session: AsyncSession):
    from bot.handlers.pool import cmd_pending

    await _seed_user(db_session, 60010)
    message = _make_message(user_id=60010)
    await cmd_pending(message=message, session=db_session)

    message.answer.assert_called_once()
    assert "no pending" in message.answer.call_args[0][0].lower()


# ── /pending (with subjects) ──────────────────────────────────────────────────


async def test_pending_shows_subjects(db_session: AsyncSession):
    from bot.handlers.pool import cmd_pending

    user_id = 60011
    await _seed_user(db_session, user_id)
    db_session.add(_subject(user_id, "Pending idea A", SubjectStatus.pending_approval))
    db_session.add(_subject(user_id, "Pending idea B", SubjectStatus.pending_approval))
    await db_session.commit()

    message = _make_message(user_id=user_id)
    await cmd_pending(message=message, session=db_session)

    assert message.answer.call_count == 2


# ── pending:approve ───────────────────────────────────────────────────────────


async def test_pending_approve_sets_active(db_session: AsyncSession):
    from bot.handlers.pool import pending_approve

    user_id = 60012
    await _seed_user(db_session, user_id)
    subject = _subject(user_id, "To approve", SubjectStatus.pending_approval)
    db_session.add(subject)
    await db_session.flush()
    subject_id = str(subject.subject_id)

    mock_vs = MagicMock()
    mock_vs.upsert_subject = AsyncMock()

    callback = _make_callback(data=f"pending:approve:{subject_id}", user_id=user_id)
    await pending_approve(callback=callback, session=db_session, vector_store=mock_vs)

    await db_session.refresh(subject)
    assert subject.status == SubjectStatus.active
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── pending:reject ────────────────────────────────────────────────────────────


async def test_pending_reject_sets_archived(db_session: AsyncSession):
    from bot.handlers.pool import pending_reject

    user_id = 60013
    await _seed_user(db_session, user_id)
    subject = _subject(user_id, "To reject", SubjectStatus.pending_approval)
    db_session.add(subject)
    await db_session.flush()
    subject_id = str(subject.subject_id)

    callback = _make_callback(data=f"pending:reject:{subject_id}", user_id=user_id)
    await pending_reject(callback=callback, session=db_session)

    await db_session.refresh(subject)
    assert subject.status == SubjectStatus.archived
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()
