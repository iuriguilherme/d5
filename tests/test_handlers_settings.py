"""Tests for /settings handler."""
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import HeuristicProfile, User
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG


async def _seed_user_and_profile(session: AsyncSession, user_id: int) -> tuple[User, HeuristicProfile]:
    user = User(user_id=user_id, cooldown_days=14)
    session.add(user)
    await session.flush()
    profile = HeuristicProfile(user_id=user_id, config=dict(DEFAULT_HEURISTIC_CONFIG))
    session.add(profile)
    await session.flush()
    return user, profile


def _make_message(user_id: int = 1, text: str = "") -> MagicMock:
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
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(**data) -> MagicMock:
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


# ── /settings ─────────────────────────────────────────────────────────────────


async def test_settings_shows_heuristics(db_session: AsyncSession):
    from bot.handlers.settings import cmd_settings

    user_id = 96001
    await _seed_user_and_profile(db_session, user_id)

    message = _make_message(user_id=user_id)
    await cmd_settings(message=message, session=db_session)

    message.answer.assert_called_once()
    # Keyboard should include heuristic buttons
    kb = message.answer.call_args[1]["reply_markup"]
    # Flatten all button texts
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Recency" in t for t in all_texts)
    assert any("Cooldown" in t for t in all_texts)


async def test_settings_shows_cooldown_button(db_session: AsyncSession):
    from bot.handlers.settings import cmd_settings

    user_id = 96002
    await _seed_user_and_profile(db_session, user_id)

    message = _make_message(user_id=user_id)
    await cmd_settings(message=message, session=db_session)

    kb = message.answer.call_args[1]["reply_markup"]
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("cooldown" in t.lower() for t in all_texts)


# ── weight update ─────────────────────────────────────────────────────────────


async def test_settings_update_weight_persists(db_session: AsyncSession):
    from bot.handlers.settings import settings_update_weight

    user_id = 96003
    _, profile = await _seed_user_and_profile(db_session, user_id)

    callback = _make_callback(data="settings:weight:recency:high", user_id=user_id)
    await settings_update_weight(callback=callback, session=db_session)

    await db_session.refresh(profile)
    assert profile.config["recency"] == "high"
    callback.answer.assert_called_once()


async def test_settings_update_weight_shows_checkmark(db_session: AsyncSession):
    from bot.handlers.settings import settings_update_weight

    user_id = 96004
    await _seed_user_and_profile(db_session, user_id)

    callback = _make_callback(data="settings:weight:novelty:low", user_id=user_id)
    await settings_update_weight(callback=callback, session=db_session)

    callback.message.edit_reply_markup.assert_called_once()
    kb = callback.message.edit_reply_markup.call_args[1]["reply_markup"]
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    # "Low" button for novelty should now have the checkmark
    assert any("✓" in t and "Low" in t for t in all_texts)


# ── cooldown FSM ──────────────────────────────────────────────────────────────


async def test_settings_cooldown_callback_sets_state():
    from bot.handlers.settings import settings_set_cooldown

    callback = _make_callback(data="settings:cooldown")
    state = _make_state()
    await settings_set_cooldown(callback=callback, state=state)

    state.set_state.assert_called_once()
    callback.message.answer.assert_called_once()
    callback.answer.assert_called_once()


async def test_settings_cooldown_valid_persists(db_session: AsyncSession):
    from bot.handlers.settings import settings_receive_cooldown

    user_id = 96005
    user = User(user_id=user_id, cooldown_days=14)
    db_session.add(user)
    await db_session.flush()

    message = _make_message(user_id=user_id, text="7")
    state = _make_state()
    await settings_receive_cooldown(message=message, state=state, session=db_session)

    await db_session.refresh(user)
    assert user.cooldown_days == 7
    state.clear.assert_called_once()
    message.answer.assert_called_once()
    assert "7" in message.answer.call_args[0][0]


async def test_settings_cooldown_invalid_reprompts(db_session: AsyncSession):
    from bot.handlers.settings import settings_receive_cooldown

    user_id = 96006
    user = User(user_id=user_id, cooldown_days=14)
    db_session.add(user)
    await db_session.flush()

    message = _make_message(user_id=user_id, text="abc")
    state = _make_state()
    await settings_receive_cooldown(message=message, state=state, session=db_session)

    await db_session.refresh(user)
    assert user.cooldown_days == 14  # unchanged
    state.clear.assert_not_called()
    message.answer.assert_called_once()
    assert "invalid" in message.answer.call_args[0][0].lower()


async def test_settings_cooldown_out_of_range(db_session: AsyncSession):
    from bot.handlers.settings import settings_receive_cooldown

    user_id = 96007
    user = User(user_id=user_id, cooldown_days=14)
    db_session.add(user)
    await db_session.flush()

    message = _make_message(user_id=user_id, text="999")
    state = _make_state()
    await settings_receive_cooldown(message=message, state=state, session=db_session)

    await db_session.refresh(user)
    assert user.cooldown_days == 14  # unchanged
    state.clear.assert_not_called()
