"""Handler for /import — wizard to upload and process a platform data export."""
import logging
from pathlib import Path
from uuid import uuid4

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

from bot.services.import_ import MAX_FILE_BYTES, ImportService

logger = logging.getLogger(__name__)

router = Router(name="import")

PLATFORMS = ["instagram", "tiktok", "threads", "other"]


class ImportStates(StatesGroup):
    waiting_for_platform = State()
    waiting_for_file = State()


# ── Keyboards ─────────────────────────────────────────────────────────────────


def _platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p.title(), callback_data=f"import:platform:{p}")]
            for p in PLATFORMS
        ]
    )


# ── /import ───────────────────────────────────────────────────────────────────


@router.message(Command("import"))
async def cmd_import(message: Message, state: FSMContext) -> None:
    await state.set_state(ImportStates.waiting_for_platform)
    await message.answer(
        "Which platform's export are you uploading?",
        reply_markup=_platform_keyboard(),
    )


@router.callback_query(F.data.startswith("import:platform:"))
async def import_select_platform(callback: CallbackQuery, state: FSMContext) -> None:
    platform = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.update_data(platform=platform)
    await state.set_state(ImportStates.waiting_for_file)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Send me your <b>{platform.title()}</b> export ZIP file.\n\n"
        "Maximum size: 20 MB. Export instructions vary by platform.",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@router.message(ImportStates.waiting_for_file, F.document)
async def import_receive_file(
    message: Message,
    state: FSMContext,
    import_service: ImportService,
    bot,
) -> None:
    doc = message.document
    if doc is None:
        await message.answer("Please send a file.")
        return

    if doc.file_size is not None and doc.file_size > MAX_FILE_BYTES:
        await message.answer(
            "File too large (max 20 MB). Please compress it and try again."
        )
        await state.clear()
        return

    data = await state.get_data()
    user_id = message.from_user.id  # type: ignore[union-attr]
    batch_id = uuid4()

    # Download to data_dir
    from bot.config import Settings

    # Resolve the data_dir from import_service
    data_dir: Path = import_service.data_dir
    dest_dir = data_dir / "imports" / str(user_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{batch_id}.zip"

    await bot.download(doc, destination=str(dest_path))

    await message.answer("File received. Processing your import...")
    await state.clear()

    try:
        batch = await import_service.process(
            user_id=user_id,
            batch_id=batch_id,
            file_path=dest_path,
            bot=bot,
        )
        await message.answer(
            f"Import complete! {batch.record_count} posts imported from "
            f"<b>{batch.platform.title()}</b>.",
            parse_mode="HTML",
        )
    except ValueError as exc:
        logger.warning("import_format_unknown", error=str(exc))
        await message.answer(
            "Could not recognize the file format. Make sure you're uploading "
            "the correct export ZIP for the selected platform."
        )
