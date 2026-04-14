"""Handler for /suggest — on-demand suggestion."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.suggestion import NoSubjectAvailableError, SuggestionEngine

router = Router(name="suggest")


@router.message(Command("suggest"))
async def cmd_suggest(
    message: Message,
    suggestion_engine: SuggestionEngine,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        subject = await suggestion_engine.suggest(user_id=user_id)
        await message.answer(
            f"<b>Suggested:</b> {subject.text}\n\nUse /posted to log what you post.",
            parse_mode="HTML",
        )
    except NoSubjectAvailableError as e:
        await message.answer(str(e))
