"""Handler for /schedule — view and modify reminder schedules."""
import logging
from uuid import UUID

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
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Reminder
from bot.services.scheduler_svc import SchedulerService
from bot.services.suggestion import NoSubjectAvailableError, SuggestionEngine

logger = logging.getLogger(__name__)

router = Router(name="schedule")


class ScheduleStates(StatesGroup):
    waiting_for_cron = State()


# ── Keyboards ─────────────────────────────────────────────────────────────────


def _reminder_keyboard(reminder: Reminder) -> InlineKeyboardMarkup:
    rid = str(reminder.reminder_id)
    if reminder.active:
        toggle = InlineKeyboardButton(text="Pause", callback_data=f"sched:pause:{rid}")
    else:
        toggle = InlineKeyboardButton(text="Resume", callback_data=f"sched:resume:{rid}")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Edit", callback_data=f"sched:edit:{rid}"),
                toggle,
            ]
        ]
    )


def _add_reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add reminder", callback_data="sched:add")]
        ]
    )


def _suggestion_keyboard(reminder_id: UUID, subject_id: str) -> InlineKeyboardMarkup:
    rid = str(reminder_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Post this", callback_data=f"sched:post:{rid}:{subject_id}"
                ),
                InlineKeyboardButton(
                    text="Skip", callback_data=f"sched:skip:{rid}:{subject_id}"
                ),
                InlineKeyboardButton(
                    text="Suggest another",
                    callback_data=f"sched:another:{rid}:{subject_id}",
                ),
            ]
        ]
    )


# ── /schedule ─────────────────────────────────────────────────────────────────


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, session: AsyncSession) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    stmt = select(Reminder).where(Reminder.user_id == user_id).order_by(
        Reminder.platform
    )
    reminders = (await session.execute(stmt)).scalars().all()

    if not reminders:
        await message.answer(
            "No reminders configured. Use /start to create defaults.",
            reply_markup=_add_reminder_keyboard(),
        )
        return

    await message.answer("<b>Your reminders:</b>", parse_mode="HTML")
    for reminder in reminders:
        status = "active" if reminder.active else "paused"
        text = (
            f"<b>{reminder.platform.title()}</b> — {reminder.schedule_expression} "
            f"[{status}]"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=_reminder_keyboard(reminder),
        )


# ── Edit flow ─────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("sched:edit:"))
async def sched_edit(callback: CallbackQuery, state: FSMContext) -> None:
    reminder_id = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.set_state(ScheduleStates.waiting_for_cron)
    await state.update_data(reminder_id=reminder_id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Send the new cron expression (e.g. <code>0 9 * * 1-5</code>).",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@router.message(ScheduleStates.waiting_for_cron)
async def sched_receive_cron(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    scheduler_service: SchedulerService,
) -> None:
    expr = (message.text or "").strip()

    # Validate cron expression before touching DB
    try:
        CronTrigger.from_crontab(expr)
    except (ValueError, KeyError):
        await message.answer(
            f"Invalid cron expression: <code>{expr}</code>\n"
            "Try again or send /schedule to cancel.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    reminder_id = UUID(data["reminder_id"])

    reminder = await session.get(Reminder, reminder_id)
    if reminder is None:
        await message.answer("Reminder not found.")
        await state.clear()
        return

    reminder.schedule_expression = expr
    await session.commit()

    if reminder.active:
        await scheduler_service.reschedule_reminder(reminder_id, expr)

    await state.clear()
    await message.answer(
        f"Updated! New schedule: <code>{expr}</code>",
        parse_mode="HTML",
    )


# ── Pause / Resume ────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("sched:pause:"))
async def sched_pause(
    callback: CallbackQuery,
    session: AsyncSession,
    scheduler_service: SchedulerService,
) -> None:
    reminder_id = UUID(callback.data.split(":")[-1])  # type: ignore[union-attr]
    reminder = await session.get(Reminder, reminder_id)
    if reminder:
        reminder.active = False
        await session.commit()
        await scheduler_service.remove_reminder(reminder_id)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Paused: <b>{reminder.platform.title() if reminder else 'reminder'}</b> — "
        f"{reminder.schedule_expression if reminder else ''}",
        parse_mode="HTML",
        reply_markup=_reminder_keyboard(reminder) if reminder else None,
    )
    await callback.answer("Paused.")


@router.callback_query(F.data.startswith("sched:resume:"))
async def sched_resume(
    callback: CallbackQuery,
    session: AsyncSession,
    scheduler_service: SchedulerService,
) -> None:
    reminder_id = UUID(callback.data.split(":")[-1])  # type: ignore[union-attr]
    reminder = await session.get(Reminder, reminder_id)
    if reminder:
        reminder.active = True
        await session.commit()
        await scheduler_service.add_reminder(reminder)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Resumed: <b>{reminder.platform.title() if reminder else 'reminder'}</b> — "
        f"{reminder.schedule_expression if reminder else ''}",
        parse_mode="HTML",
        reply_markup=_reminder_keyboard(reminder) if reminder else None,
    )
    await callback.answer("Resumed.")


# ── Reminder fire handler (called by APScheduler) ─────────────────────────────


async def reminder_fire_handler(
    reminder_id: UUID,
    *,
    session_factory,
    suggestion_engine: SuggestionEngine,
    bot,
    user_id: int,
) -> None:
    """Fire a scheduled reminder: suggest a subject and send to user."""
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import AsyncSession

    async with session_factory() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder is None or not reminder.active:
            return

        try:
            subject = await suggestion_engine.suggest(user_id=user_id)
        except NoSubjectAvailableError:
            await bot.send_message(
                user_id,
                "All subjects are in cooldown — add new ideas with /idea or "
                "reduce cooldown in /settings.",
            )
            return

        reminder.last_fired_at = datetime.now(timezone.utc)
        await session.commit()

    subject_id = str(subject.subject_id)
    await bot.send_message(
        user_id,
        f"Time to post! Suggested subject:\n\n<b>{subject.text}</b>",
        parse_mode="HTML",
        reply_markup=_suggestion_keyboard(reminder_id, subject_id),
    )


# ── Post / Skip / Another callbacks ──────────────────────────────────────────


@router.callback_query(F.data.startswith("sched:post:"))
async def sched_post(callback: CallbackQuery) -> None:
    """User chose 'Post this' from a reminder suggestion.

    Remove the suggestion keyboard and prompt them to log via /posted.
    """
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Great! Use /posted to log what you posted.",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sched:skip:"))
async def sched_skip(callback: CallbackQuery, session: AsyncSession) -> None:
    from datetime import datetime, timezone

    from bot.models import Post
    from bot.models.post import PostPlatform, PostSource
    from uuid import UUID

    # callback data: sched:skip:{reminder_id}:{subject_id}
    parts = callback.data.split(":")  # type: ignore[union-attr]
    reminder_id = UUID(parts[2])
    subject_id = UUID(parts[3])
    user_id = callback.from_user.id  # type: ignore[union-attr]

    reminder = await session.get(Reminder, reminder_id)

    post = Post(
        user_id=user_id,
        subject_id=subject_id,
        platform=PostPlatform(reminder.platform if reminder else "other"),
        source=PostSource.skipped,
        posted_at=datetime.now(timezone.utc),
    )
    session.add(post)
    await session.commit()

    await callback.message.edit_text(  # type: ignore[union-attr]
        "Skipped. The subject stays in your pool for next time.",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sched:another:"))
async def sched_another(
    callback: CallbackQuery,
    session: AsyncSession,
    suggestion_engine: SuggestionEngine,
) -> None:
    from uuid import UUID

    parts = callback.data.split(":")  # type: ignore[union-attr]
    reminder_id = UUID(parts[2])
    excluded_subject_id = UUID(parts[3])
    user_id = callback.from_user.id  # type: ignore[union-attr]

    try:
        subject = await suggestion_engine.suggest(
            user_id=user_id,
            exclude_ids=[excluded_subject_id],
        )
    except NoSubjectAvailableError:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "No more subjects available right now. Add ideas with /idea.",
            reply_markup=None,
        )
        await callback.answer()
        return

    subject_id = str(subject.subject_id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"How about this instead:\n\n<b>{subject.text}</b>",
        parse_mode="HTML",
        reply_markup=_suggestion_keyboard(reminder_id, subject_id),
    )
    await callback.answer()
