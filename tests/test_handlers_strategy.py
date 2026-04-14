"""Tests for /strategy handler."""
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import StrategyNote, User


async def _seed_user(session: AsyncSession, user_id: int) -> User:
    user = User(user_id=user_id)
    session.add(user)
    await session.flush()
    return user


def _make_message(user_id: int = 1, text: str = "strategy text") -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
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


# ── cmd_strategy ──────────────────────────────────────────────────────────────


async def test_cmd_strategy_sets_state():
    from bot.handlers.strategy import cmd_strategy

    message = _make_message()
    state = _make_state()
    await cmd_strategy(message=message, state=state)

    state.set_state.assert_called_once()
    message.answer.assert_called_once()


# ── strategy_receive_text ─────────────────────────────────────────────────────


async def test_strategy_receive_text_asks_confirm():
    from bot.handlers.strategy import strategy_receive_text

    message = _make_message(text="My content strategy")
    state = _make_state()
    await strategy_receive_text(message=message, state=state)

    state.update_data.assert_called_once_with(text="My content strategy")
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


async def test_strategy_receive_text_empty_rejected():
    from bot.handlers.strategy import strategy_receive_text

    message = _make_message(text="   ")
    state = _make_state()
    await strategy_receive_text(message=message, state=state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()


async def test_strategy_receive_text_long_accepted():
    from bot.handlers.strategy import strategy_receive_text

    long_text = "x" * 2000
    message = _make_message(text=long_text)
    state = _make_state()
    await strategy_receive_text(message=message, state=state)

    state.update_data.assert_called_once_with(text=long_text)


# ── strategy_save ─────────────────────────────────────────────────────────────


async def test_strategy_save_creates_note(db_session: AsyncSession):
    from bot.handlers.strategy import strategy_save

    user_id = 95001
    await _seed_user(db_session, user_id)

    text = "Focus on short-form video content about cooking"
    callback = _make_callback(data="strategy:save", user_id=user_id)
    state = _make_state(text=text)

    mock_pred = MagicMock()
    mock_pred.embed_text = AsyncMock(return_value=[0.1] * 384)

    mock_vs = MagicMock()
    mock_vs.upsert_strategy = AsyncMock()

    await strategy_save(
        callback=callback,
        state=state,
        session=db_session,
        prediction_service=mock_pred,
        vector_store=mock_vs,
    )

    notes = (
        await db_session.execute(
            select(StrategyNote).where(StrategyNote.user_id == user_id)
        )
    ).scalars().all()
    assert len(notes) == 1
    assert notes[0].text == text
    assert notes[0].embedding_id is not None

    mock_vs.upsert_strategy.assert_called_once()
    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    assert "saved" in callback.message.edit_text.call_args[0][0].lower()


# ── strategy_cancel ───────────────────────────────────────────────────────────


async def test_strategy_cancel_clears_state():
    from bot.handlers.strategy import strategy_cancel

    callback = _make_callback(data="strategy:cancel")
    state = _make_state()
    await strategy_cancel(callback=callback, state=state)

    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()
