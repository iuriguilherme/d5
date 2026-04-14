"""Handler for /posted — FSM to record a post."""
from datetime import datetime, timezone

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
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Post, Subject
from bot.models.post import PostPlatform, PostSource
from bot.models.subject import SubjectStatus

router = Router(name="posted")

PLATFORMS = ["instagram", "tiktok", "threads", "other"]


class PostedStates(StatesGroup):
    waiting_for_subject = State()
    waiting_for_platform = State()
    waiting_for_caption = State()


def _platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p.title(), callback_data=f"posted:platform:{p}")]
            for p in PLATFORMS
        ]
    )


def _subject_keyboard(subjects: list[Subject]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=s.text[:40], callback_data=f"posted:subject:{s.subject_id}")]
        for s in subjects
    ]
    buttons.append(
        [InlineKeyboardButton(text="None of these", callback_data="posted:subject:none")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _caption_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Skip", callback_data="posted:caption:skip"),
                InlineKeyboardButton(text="Add caption", callback_data="posted:caption:add"),
            ]
        ]
    )


@router.message(Command("posted"))
async def cmd_posted(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    from sqlalchemy import select

    stmt = select(Subject).where(
        Subject.user_id == user_id,
        Subject.status == SubjectStatus.active,
    )
    subjects = (await session.execute(stmt)).scalars().all()

    if not subjects:
        # No subjects — skip to platform selection
        await state.set_state(PostedStates.waiting_for_platform)
        await state.update_data(subject_id=None)
        await message.answer("What did you post on?", reply_markup=_platform_keyboard())
        return

    await state.set_state(PostedStates.waiting_for_subject)
    await message.answer(
        "What did you post? Describe it briefly and I'll find the matching subject.",
    )


@router.message(PostedStates.waiting_for_subject)
async def posted_match_subject(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from sqlalchemy import select

    text = (message.text or "").strip()
    user_id = message.from_user.id  # type: ignore[union-attr]

    # Semantic match via ChromaDB — requires vector_store injected in data
    # Simplified: fetch top 3 by text similarity (placeholder — real impl uses VectorStore)
    stmt = select(Subject).where(
        Subject.user_id == user_id,
        Subject.status == SubjectStatus.active,
    ).limit(3)
    candidates = (await session.execute(stmt)).scalars().all()

    await state.update_data(search_text=text)
    await state.set_state(PostedStates.waiting_for_platform)
    await state.update_data(subject_id=None)

    if candidates:
        await message.answer(
            "Which subject matches what you posted?",
            reply_markup=_subject_keyboard(candidates),
        )
    else:
        await message.answer("Which platform did you post on?", reply_markup=_platform_keyboard())


@router.callback_query(F.data.startswith("posted:subject:"))
async def posted_select_subject(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[-1]  # type: ignore[union-attr]
    subject_id = None if value == "none" else value
    await state.update_data(subject_id=subject_id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Which platform did you post on?",
        reply_markup=_platform_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("posted:platform:"))
async def posted_select_platform(callback: CallbackQuery, state: FSMContext) -> None:
    platform = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.update_data(platform=platform)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Want to add a caption excerpt?",
        reply_markup=_caption_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "posted:caption:skip")
async def posted_caption_skip(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _finalize_post(callback, state, session, caption=None)


@router.callback_query(F.data == "posted:caption:add")
async def posted_caption_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostedStates.waiting_for_caption)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Send me a brief caption excerpt.",
        reply_markup=None,
    )
    await callback.answer()


@router.message(PostedStates.waiting_for_caption)
async def posted_receive_caption(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    caption = (message.text or "").strip() or None
    await _finalize_post_msg(message, state, session, caption=caption)


async def _finalize_post(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    caption: str | None,
) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id  # type: ignore[union-attr]
    platform = data.get("platform", "other")
    subject_id_str = data.get("subject_id")

    from uuid import UUID

    subject = None
    if subject_id_str:
        subject = await session.get(Subject, UUID(subject_id_str))

    post = Post(
        user_id=user_id,
        subject_id=UUID(subject_id_str) if subject_id_str else None,
        platform=PostPlatform(platform),
        source=PostSource.manual_confirm,
        posted_at=datetime.now(timezone.utc),
        caption_excerpt=caption,
    )
    session.add(post)

    if subject:
        subject.last_posted_at = post.posted_at

    await session.commit()
    await state.clear()

    label = subject.text if subject else "(no subject)"
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Logged! ✓ <b>{label}</b> posted to {platform.title()}",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


async def _finalize_post_msg(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    caption: str | None,
) -> None:
    data = await state.get_data()
    user_id = message.from_user.id  # type: ignore[union-attr]
    platform = data.get("platform", "other")
    subject_id_str = data.get("subject_id")

    from uuid import UUID

    subject = None
    if subject_id_str:
        subject = await session.get(Subject, UUID(subject_id_str))

    post = Post(
        user_id=user_id,
        subject_id=UUID(subject_id_str) if subject_id_str else None,
        platform=PostPlatform(platform),
        source=PostSource.manual_confirm,
        posted_at=datetime.now(timezone.utc),
        caption_excerpt=caption,
    )
    session.add(post)

    if subject:
        subject.last_posted_at = post.posted_at

    await session.commit()
    await state.clear()

    label = subject.text if subject else "(no subject)"
    await message.answer(
        f"Logged! ✓ <b>{label}</b> posted to {platform.title()}",
        parse_mode="HTML",
    )
