"""Tests for /posted FSM handler."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Post, Subject, User
from bot.models.post import PostPlatform, PostSource
from bot.models.subject import SubjectSource, SubjectStatus


async def _seed_user(session: AsyncSession, user_id: int) -> User:
    user = User(user_id=user_id)
    session.add(user)
    await session.flush()
    return user


async def _seed_subject(
    session: AsyncSession,
    user_id: int,
    text: str = "test subject",
    status: SubjectStatus = SubjectStatus.active,
) -> Subject:
    subject = Subject(
        user_id=user_id,
        text=text,
        source=SubjectSource.manual,
        status=status,
    )
    session.add(subject)
    await session.flush()
    return subject


def _make_message(user_id: int = 1, text: str = "my post") -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 1) -> MagicMock:
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(**data) -> MagicMock:
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


# ── cmd_posted (no subjects) ──────────────────────────────────────────────────


async def test_posted_no_subjects_goes_to_platform(db_session: AsyncSession):
    from bot.handlers.posted import cmd_posted

    user_id = 70001
    await _seed_user(db_session, user_id)

    message = _make_message(user_id=user_id)
    state = _make_state()

    await cmd_posted(message=message, state=state, session=db_session)

    # Should jump to platform select, not subject select
    state.set_state.assert_called_once()
    state.update_data.assert_called_with(subject_id=None)
    message.answer.assert_called_once()
    assert "post" in message.answer.call_args[0][0].lower()


# ── cmd_posted (with subjects) ────────────────────────────────────────────────


async def test_posted_with_subjects_asks_for_description(db_session: AsyncSession):
    from bot.handlers.posted import cmd_posted

    user_id = 70002
    await _seed_user(db_session, user_id)
    await _seed_subject(db_session, user_id)

    message = _make_message(user_id=user_id)
    state = _make_state()

    await cmd_posted(message=message, state=state, session=db_session)

    state.set_state.assert_called_once()
    message.answer.assert_called_once()


# ── posted_match_subject ──────────────────────────────────────────────────────


async def test_posted_match_subject_shows_candidates(db_session: AsyncSession):
    from bot.handlers.posted import posted_match_subject

    user_id = 70003
    await _seed_user(db_session, user_id)
    await _seed_subject(db_session, user_id, "cooking tips")

    message = _make_message(user_id=user_id, text="cooking")
    state = _make_state()

    await posted_match_subject(message=message, state=state, session=db_session)

    state.update_data.assert_any_call(search_text="cooking")
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


async def test_posted_match_subject_no_candidates_shows_platform(db_session: AsyncSession):
    from bot.handlers.posted import posted_match_subject

    user_id = 70004
    await _seed_user(db_session, user_id)
    # No subjects in DB

    message = _make_message(user_id=user_id, text="something")
    state = _make_state()

    await posted_match_subject(message=message, state=state, session=db_session)

    message.answer.assert_called_once()


# ── posted_select_subject ─────────────────────────────────────────────────────


async def test_posted_select_subject_stores_id():
    from bot.handlers.posted import posted_select_subject
    import uuid

    subject_id = str(uuid.uuid4())
    callback = _make_callback(data=f"posted:subject:{subject_id}")
    state = _make_state()

    await posted_select_subject(callback=callback, state=state)

    state.update_data.assert_called_with(subject_id=subject_id)
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


async def test_posted_select_subject_none():
    from bot.handlers.posted import posted_select_subject

    callback = _make_callback(data="posted:subject:none")
    state = _make_state()

    await posted_select_subject(callback=callback, state=state)

    state.update_data.assert_called_with(subject_id=None)


# ── posted_select_platform ────────────────────────────────────────────────────


async def test_posted_select_platform_stores_and_asks_caption():
    from bot.handlers.posted import posted_select_platform

    callback = _make_callback(data="posted:platform:instagram")
    state = _make_state()

    await posted_select_platform(callback=callback, state=state)

    state.update_data.assert_called_with(platform="instagram")
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── posted_caption_skip (no subject) ─────────────────────────────────────────


async def test_posted_caption_skip_creates_post(db_session: AsyncSession):
    from bot.handlers.posted import posted_caption_skip

    user_id = 70010
    await _seed_user(db_session, user_id)

    callback = _make_callback(data="posted:caption:skip", user_id=user_id)
    state = _make_state(platform="instagram", subject_id=None)

    await posted_caption_skip(callback=callback, state=state, session=db_session)

    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 1
    assert posts[0].platform == PostPlatform.instagram
    assert posts[0].source == PostSource.manual_confirm
    assert posts[0].caption_excerpt is None
    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()


# ── posted_caption_skip (with subject) ───────────────────────────────────────


async def test_posted_caption_skip_updates_subject_last_posted(db_session: AsyncSession):
    from bot.handlers.posted import posted_caption_skip

    user_id = 70011
    await _seed_user(db_session, user_id)
    subject = await _seed_subject(db_session, user_id)
    subject_id_str = str(subject.subject_id)

    callback = _make_callback(data="posted:caption:skip", user_id=user_id)
    state = _make_state(platform="tiktok", subject_id=subject_id_str)

    await posted_caption_skip(callback=callback, state=state, session=db_session)

    await db_session.refresh(subject)
    assert subject.last_posted_at is not None

    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 1
    assert posts[0].subject_id == subject.subject_id


# ── posted_caption_add ────────────────────────────────────────────────────────


async def test_posted_caption_add_sets_state():
    from bot.handlers.posted import posted_caption_add

    callback = _make_callback(data="posted:caption:add")
    state = _make_state()

    await posted_caption_add(callback=callback, state=state)

    state.set_state.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── posted_receive_caption ────────────────────────────────────────────────────


async def test_posted_receive_caption_creates_post_with_caption(db_session: AsyncSession):
    from bot.handlers.posted import posted_receive_caption

    user_id = 70012
    await _seed_user(db_session, user_id)

    message = _make_message(user_id=user_id, text="My caption excerpt")
    state = _make_state(platform="threads", subject_id=None)

    await posted_receive_caption(message=message, state=state, session=db_session)

    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 1
    assert posts[0].caption_excerpt == "My caption excerpt"
    assert posts[0].platform == PostPlatform.threads
    state.clear.assert_called_once()
    message.answer.assert_called_once()
