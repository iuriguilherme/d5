"""Handlers for /start and /help."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.models import HeuristicProfile, Reminder, User
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG

router = Router(name="start")

# Default reminder schedule: one per platform, weekday mornings (UTC)
DEFAULT_REMINDERS = [
    {"platform": "instagram", "schedule_expression": "0 9 * * 1-5"},
    {"platform": "tiktok", "schedule_expression": "0 12 * * 1-5"},
    {"platform": "threads", "schedule_expression": "0 18 * * 1-5"},
    {"platform": "other", "schedule_expression": "0 20 * * 1-5"},
]

HELP_TEXT = """
<b>WDWGN — Where Do We Go Now</b>

<b>Commands:</b>
/idea — add a new content subject to your pool
/pool — browse your active subjects
/pending — review AI-predicted subjects for approval
/posted — record what you posted
/suggest — get an on-demand suggestion
/schedule — manage reminder schedules
/import — import posting history from platform exports
/strategy — add strategy research notes
/settings — tune suggestion weights and cooldown
/help — show this message
""".strip()


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    existing = await session.get(User, user_id)
    if existing is None:
        # First visit — create user record and flush so FK-dependents can reference it
        user = User(
            user_id=user_id,
            username=message.from_user.username,  # type: ignore[union-attr]
            first_name=message.from_user.first_name,  # type: ignore[union-attr]
        )
        session.add(user)
        await session.flush()  # user_id must exist before FK-referencing inserts

        # Seed default reminders
        for r in DEFAULT_REMINDERS:
            session.add(Reminder(user_id=user_id, **r))

        # Seed default heuristic profile
        session.add(
            HeuristicProfile(
                user_id=user_id,
                name="default",
                config=dict(DEFAULT_HEURISTIC_CONFIG),
            )
        )
        await session.commit()

        await message.answer(
            "Welcome to <b>WDWGN</b>! 👋\n\n"
            "I'll help you organize your social media content ideas and suggest "
            "what to post next.\n\n"
            "Start by adding an idea with /idea, or see all commands with /help.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "Welcome back! Use /help to see available commands.",
            parse_mode="HTML",
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")
