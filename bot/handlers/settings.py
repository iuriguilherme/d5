"""Handler for /settings — heuristic weight tuning and cooldown configuration."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.heuristics.registry import WEIGHT_VALUES
from bot.models import HeuristicProfile, User
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG

router = Router(name="settings")

WEIGHT_LEVELS = ["off", "low", "medium", "high"]
HEURISTIC_LABELS = {
    "recency": "Recency",
    "cooldown": "Cooldown",
    "strategy_align": "Strategy alignment",
    "novelty": "Novelty",
    "platform_fit": "Platform fit",
    "jitter": "Jitter",
}


class SettingsStates(StatesGroup):
    waiting_for_cooldown = State()


# ── /settings ─────────────────────────────────────────────────────────────────


def _settings_keyboard(config: dict, cooldown_days: int) -> InlineKeyboardMarkup:
    rows = []
    for key, label in HEURISTIC_LABELS.items():
        current = config.get(key, "medium")
        buttons = []
        for level in WEIGHT_LEVELS:
            marker = "✓ " if level == current else ""
            buttons.append(
                InlineKeyboardButton(
                    text=f"{marker}{level.title()}",
                    callback_data=f"settings:weight:{key}:{level}",
                )
            )
        rows.append([InlineKeyboardButton(text=f"▸ {label}", callback_data="noop")])
        rows.append(buttons)

    rows.append(
        [
            InlineKeyboardButton(
                text=f"Set cooldown ({cooldown_days} days)",
                callback_data="settings:cooldown",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    user = await session.get(User, user_id)
    cooldown_days = user.cooldown_days if user else 14

    stmt = select(HeuristicProfile).where(HeuristicProfile.user_id == user_id)
    profile = (await session.execute(stmt)).scalars().first()

    config = profile.config if profile else dict(DEFAULT_HEURISTIC_CONFIG)

    await message.answer(
        "<b>Settings</b>\n\nAdjust how your content suggestions are weighted:",
        parse_mode="HTML",
        reply_markup=_settings_keyboard(config, cooldown_days),
    )


# ── Weight updates ────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("settings:weight:"))
async def settings_update_weight(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    # callback_data: settings:weight:{heuristic}:{level}
    parts = callback.data.split(":")  # type: ignore[union-attr]
    heuristic = parts[2]
    level = parts[3]

    if level not in WEIGHT_LEVELS:
        await callback.answer("Unknown weight level.")
        return

    user_id = callback.from_user.id  # type: ignore[union-attr]

    stmt = select(HeuristicProfile).where(HeuristicProfile.user_id == user_id)
    profile = (await session.execute(stmt)).scalars().first()

    if profile is None:
        await callback.answer("No heuristic profile found. Try /start again.")
        return

    # JSON dict must be replaced (not mutated) for SQLAlchemy to detect change
    new_config = dict(profile.config)
    new_config[heuristic] = level
    profile.config = new_config
    await session.commit()

    label = HEURISTIC_LABELS.get(heuristic, heuristic)

    # Refresh keyboard with updated config
    user = await session.get(User, user_id)
    cooldown_days = user.cooldown_days if user else 14
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_settings_keyboard(new_config, cooldown_days)
    )
    await callback.answer(f"Updated {label} → {level.title()}")


# ── Cooldown ──────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "settings:cooldown")
async def settings_set_cooldown(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_for_cooldown)
    await callback.message.answer(  # type: ignore[union-attr]
        "Send the cooldown period in days (1–365):"
    )
    await callback.answer()


@router.message(SettingsStates.waiting_for_cooldown)
async def settings_receive_cooldown(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    try:
        days = int(text)
        if not (1 <= days <= 365):
            raise ValueError
    except ValueError:
        await message.answer(
            "Invalid value. Please send a number between 1 and 365."
        )
        return

    user_id = message.from_user.id  # type: ignore[union-attr]
    user = await session.get(User, user_id)
    if user:
        user.cooldown_days = days
        await session.commit()

    await state.clear()
    await message.answer(
        f"Cooldown updated to <b>{days} days</b>.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    """No-op handler for label-only buttons."""
    await callback.answer()
