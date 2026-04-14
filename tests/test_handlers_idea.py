"""Tests for /idea FSM handler."""
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Subject, User
from bot.models.subject import SubjectStatus


async def _seed_user(session: AsyncSession, user_id: int) -> User:
    user = User(user_id=user_id)
    session.add(user)
    await session.flush()
    return user


def _make_state(**data) -> MagicMock:
    """Return a mock FSMContext with preset get_data return value."""
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


def _make_message(user_id: int = 1, text: str = "test idea") -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_callback(user_id: int = 1, data: str = "idea:save") -> MagicMock:
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# ── cmd_idea ──────────────────────────────────────────────────────────────────


async def test_cmd_idea_sets_state():
    from bot.handlers.idea import cmd_idea

    message = _make_message()
    state = _make_state()

    await cmd_idea(message=message, state=state)

    state.set_state.assert_called_once()
    message.answer.assert_called_once()


# ── idea_receive_text ─────────────────────────────────────────────────────────


async def test_idea_receive_text_stores_and_confirms():
    from bot.handlers.idea import idea_receive_text

    message = _make_message(text="My great idea")
    state = _make_state()

    await idea_receive_text(message=message, state=state)

    state.update_data.assert_called_once_with(text="My great idea")
    state.set_state.assert_called_once()
    message.answer.assert_called_once()
    # Should include the idea text in the reply
    call_text = message.answer.call_args[0][0]
    assert "My great idea" in call_text


async def test_idea_receive_text_empty_rejects():
    from bot.handlers.idea import idea_receive_text

    message = _make_message(text="   ")
    state = _make_state()

    await idea_receive_text(message=message, state=state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()


# ── idea_save ─────────────────────────────────────────────────────────────────


async def test_idea_save_creates_subject(db_session: AsyncSession):
    from bot.handlers.idea import idea_save

    # Arrange
    user_id = 55001
    await _seed_user(db_session, user_id)
    text = "Unique content idea for test"
    callback = _make_callback(user_id=user_id, data="idea:save")
    state = _make_state(text=text)

    mock_pred = MagicMock()
    mock_pred.embed_text = AsyncMock(return_value=[0.1] * 384)

    mock_vs = MagicMock()
    mock_vs.upsert_subject = AsyncMock()

    await idea_save(
        callback=callback,
        state=state,
        session=db_session,
        prediction_service=mock_pred,
        vector_store=mock_vs,
    )

    # Subject should be in DB
    subjects = (
        await db_session.execute(
            select(Subject).where(
                Subject.user_id == user_id,
                Subject.status == SubjectStatus.active,
            )
        )
    ).scalars().all()
    assert len(subjects) == 1
    assert subjects[0].text == text

    # Vector store should have been called
    mock_vs.upsert_subject.assert_called_once()
    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()


async def test_idea_save_embeds_and_stores_embedding_id(db_session: AsyncSession):
    from bot.handlers.idea import idea_save

    user_id = 55002
    await _seed_user(db_session, user_id)
    text = "Another idea"
    callback = _make_callback(user_id=user_id)
    state = _make_state(text=text)

    mock_pred = MagicMock()
    mock_pred.embed_text = AsyncMock(return_value=[0.5] * 384)

    mock_vs = MagicMock()
    mock_vs.upsert_subject = AsyncMock()

    await idea_save(
        callback=callback,
        state=state,
        session=db_session,
        prediction_service=mock_pred,
        vector_store=mock_vs,
    )

    subjects = (
        await db_session.execute(
            select(Subject).where(Subject.user_id == user_id)
        )
    ).scalars().all()
    assert subjects[0].embedding_id is not None


# ── idea_edit ─────────────────────────────────────────────────────────────────


async def test_idea_edit_resets_to_waiting_for_text():
    from bot.handlers.idea import idea_edit

    callback = _make_callback(data="idea:edit")
    state = _make_state()

    await idea_edit(callback=callback, state=state)

    state.set_state.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── idea_cancel ───────────────────────────────────────────────────────────────


async def test_idea_cancel_clears_state():
    from bot.handlers.idea import idea_cancel

    callback = _make_callback(data="idea:cancel")
    state = _make_state()

    await idea_cancel(callback=callback, state=state)

    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()
