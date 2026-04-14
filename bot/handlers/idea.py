"""Handler for /idea — FSM flow to add a new content subject."""
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

from bot.models import Subject
from bot.models.subject import SubjectSource, SubjectStatus
from bot.services.prediction import PredictionService
from bot.vector.client import VectorStore

router = Router(name="idea")


class IdeaStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirm = State()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Save", callback_data="idea:save"),
                InlineKeyboardButton(text="Edit", callback_data="idea:edit"),
                InlineKeyboardButton(text="Cancel", callback_data="idea:cancel"),
            ]
        ]
    )


@router.message(Command("idea"))
async def cmd_idea(message: Message, state: FSMContext) -> None:
    await state.set_state(IdeaStates.waiting_for_text)
    await message.answer("What's your content idea? Send me the subject text.")


@router.message(IdeaStates.waiting_for_text)
async def idea_receive_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Please send some text for your idea.")
        return
    await state.update_data(text=text)
    await state.set_state(IdeaStates.waiting_for_confirm)
    await message.answer(
        f"Your idea:\n\n<b>{text}</b>\n\nSave it?",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(IdeaStates.waiting_for_confirm, F.data == "idea:save")
async def idea_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    prediction_service: PredictionService,
    vector_store: VectorStore,
) -> None:
    data = await state.get_data()
    text = data.get("text", "")
    user_id = callback.from_user.id

    subject = Subject(
        user_id=user_id,
        text=text,
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    session.add(subject)
    await session.flush()

    # Embed and store in ChromaDB
    embedding = await prediction_service.embed_text(text)
    await vector_store.upsert_subject(
        user_id, str(subject.subject_id), embedding, {"text": text}
    )
    subject.embedding_id = str(subject.subject_id)
    await session.commit()

    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Saved! <b>{text}</b> added to your pool.",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(IdeaStates.waiting_for_confirm, F.data == "idea:edit")
async def idea_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(IdeaStates.waiting_for_text)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Send me the updated text for your idea.",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(IdeaStates.waiting_for_confirm, F.data == "idea:cancel")
async def idea_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Idea discarded.",
        reply_markup=None,
    )
    await callback.answer()
