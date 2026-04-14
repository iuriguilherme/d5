"""Handlers for /pool and /pending."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Subject
from bot.models.subject import SubjectStatus
from bot.vector.client import VectorStore

router = Router(name="pool")

PAGE_SIZE = 5


# ── Pagination helpers ────────────────────────────────────────────────────────


def _pool_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    last_page = max(0, (total - 1) // PAGE_SIZE)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="<< Prev", callback_data=f"pool:page:{page - 1}"))
    if page < last_page:
        buttons.append(InlineKeyboardButton(text="Next >>", callback_data=f"pool:page:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


def _pending_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"pending:approve:{subject_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"pending:reject:{subject_id}"),
            ]
        ]
    )


# ── /pool ─────────────────────────────────────────────────────────────────────


@router.message(Command("pool"))
async def cmd_pool(message: Message, session: AsyncSession) -> None:
    await _send_pool_page(message, session, page=0, edit=False)


@router.callback_query(F.data.startswith("pool:page:"))
async def pool_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[-1])  # type: ignore[union-attr]
    await _send_pool_page(callback.message, session, page=page, edit=True)  # type: ignore[arg-type]
    await callback.answer()


async def _send_pool_page(
    target: Message,
    session: AsyncSession,
    page: int,
    edit: bool,
) -> None:
    user_id = (target.chat.id if edit else target.from_user.id)  # type: ignore[union-attr]

    stmt = select(Subject).where(
        Subject.user_id == user_id,
        Subject.status == SubjectStatus.active,
    ).order_by(Subject.subject_id)
    subjects = (await session.execute(stmt)).scalars().all()

    if not subjects:
        text = "Your pool is empty. Add ideas with /idea."
        if edit:
            await target.edit_text(text)
        else:
            await target.answer(text)
        return

    start = page * PAGE_SIZE
    page_items = subjects[start : start + PAGE_SIZE]
    lines = "\n".join(f"{start + i + 1}. {s.text}" for i, s in enumerate(page_items))
    text = f"<b>Your subject pool</b> ({len(subjects)} total, page {page + 1}):\n\n{lines}"

    kb = _pool_keyboard(page, len(subjects))
    if edit:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


# ── /pending ──────────────────────────────────────────────────────────────────


@router.message(Command("pending"))
async def cmd_pending(message: Message, session: AsyncSession) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    stmt = select(Subject).where(
        Subject.user_id == user_id,
        Subject.status == SubjectStatus.pending_approval,
    )
    subjects = (await session.execute(stmt)).scalars().all()

    if not subjects:
        await message.answer("No pending subjects. They appear after you use /import.")
        return

    for subject in subjects:
        await message.answer(
            f"<b>Pending idea:</b> {subject.text}",
            parse_mode="HTML",
            reply_markup=_pending_keyboard(str(subject.subject_id)),
        )


@router.callback_query(F.data.startswith("pending:approve:"))
async def pending_approve(
    callback: CallbackQuery,
    session: AsyncSession,
    vector_store: VectorStore,
) -> None:
    from uuid import UUID

    subject_id = UUID(callback.data.split(":")[-1])  # type: ignore[union-attr]
    subject = await session.get(Subject, subject_id)
    if subject:
        subject.status = SubjectStatus.active
        await session.commit()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Approved! <b>{subject.text if subject else '(unknown)'}</b> added to your pool.",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pending:reject:"))
async def pending_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    from uuid import UUID

    subject_id = UUID(callback.data.split(":")[-1])  # type: ignore[union-attr]
    subject = await session.get(Subject, subject_id)
    if subject:
        subject.status = SubjectStatus.archived
        await session.commit()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Rejected and archived.",
        reply_markup=None,
    )
    await callback.answer()
