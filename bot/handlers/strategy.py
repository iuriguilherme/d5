"""Handler for /strategy — accept strategy research text and embed it."""
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

from bot.models import StrategyNote
from bot.services.prediction import PredictionService
from bot.vector.client import VectorStore

router = Router(name="strategy")


class StrategyStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirm = State()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Save", callback_data="strategy:save"),
                InlineKeyboardButton(text="Cancel", callback_data="strategy:cancel"),
            ]
        ]
    )


@router.message(Command("strategy"))
async def cmd_strategy(message: Message, state: FSMContext) -> None:
    await state.set_state(StrategyStates.waiting_for_text)
    await message.answer(
        "Send me your content strategy research. This can be notes, "
        "audience insights, trending topics — any text that describes "
        "what you want to post about."
    )


@router.message(StrategyStates.waiting_for_text)
async def strategy_receive_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Please send some text.")
        return
    await state.update_data(text=text)
    await state.set_state(StrategyStates.waiting_for_confirm)
    preview = text[:200] + ("..." if len(text) > 200 else "")
    await message.answer(
        f"Save this strategy note?\n\n<blockquote>{preview}</blockquote>",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(StrategyStates.waiting_for_confirm, F.data == "strategy:save")
async def strategy_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    prediction_service: PredictionService,
    vector_store: VectorStore,
) -> None:
    data = await state.get_data()
    text = data.get("text", "")
    user_id = callback.from_user.id  # type: ignore[union-attr]

    note = StrategyNote(user_id=user_id, text=text)
    session.add(note)
    await session.flush()

    embedding = await prediction_service.embed_text(text)
    note_id = str(note.note_id)
    await vector_store.upsert_strategy(user_id, note_id, embedding, {"text": text[:500]})
    note.embedding_id = note_id

    await session.commit()
    await state.clear()

    await callback.message.edit_text(  # type: ignore[union-attr]
        "Strategy note saved. Suggestions will now reflect this strategy.",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(StrategyStates.waiting_for_confirm, F.data == "strategy:cancel")
async def strategy_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Cancelled.",
        reply_markup=None,
    )
    await callback.answer()
