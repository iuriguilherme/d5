"""WDWGN bot entrypoint."""
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.middleware import FSMContextMiddleware
from aiogram.types import BotCommand, TelegramObject, Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.db.engine import build_engine
from bot.db.fsm_storage import SqliteStorage
from bot.db.session import build_session_factory
from bot.handlers import start
from bot.vector.client import VectorStore

logger = structlog.get_logger(__name__)


# ── Allowlist middleware ───────────────────────────────────────────────────────


class AllowlistMiddleware:
    """Outer middleware: rejects updates from users not in ALLOWED_USER_IDS.

    When allowed_user_ids is empty the check is disabled (all users pass).
    """

    def __init__(self, allowed_user_ids: list[int]) -> None:
        self._allowed = set(allowed_user_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Any],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self._allowed:
            update: Update = data.get("event_update")  # type: ignore[assignment]
            user_id: int | None = None
            if update and update.message and update.message.from_user:
                user_id = update.message.from_user.id
            elif update and update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id

            if user_id is not None and user_id not in self._allowed:
                # Silently reject — do not call the handler
                if update and update.message:
                    await update.message.answer("Access denied.")
                return None

        return await handler(event, data)


# ── Session middleware ────────────────────────────────────────────────────────


class SessionMiddleware:
    """Injects an AsyncSession and session_factory into handler data."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Any],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._factory() as session:
            data["session"] = session
            data["session_factory"] = self._factory
            return await handler(event, data)


# ── Bot factory ───────────────────────────────────────────────────────────────


def build_dispatcher(settings: Settings, session_factory: async_sessionmaker) -> Dispatcher:
    db_path = str(settings.data_dir / "wdwgn.db")
    storage = SqliteStorage(db_path=db_path)
    dp = Dispatcher(storage=storage)

    # Outer middleware — applied before FSM context
    dp.update.outer_middleware(AllowlistMiddleware(settings.allowed_user_ids))
    dp.update.middleware(SessionMiddleware(session_factory))

    # Register routers
    dp.include_router(start.router)

    return dp


async def on_startup(
    bot: Bot,
    settings: Settings,
    scheduler,  # will be injected by scheduler unit
) -> None:
    # Register bot command menu
    await bot.set_my_commands(
        [
            BotCommand(command="idea", description="Add a content subject"),
            BotCommand(command="pool", description="Browse your subject pool"),
            BotCommand(command="pending", description="Review AI-predicted subjects"),
            BotCommand(command="posted", description="Record what you posted"),
            BotCommand(command="suggest", description="Get a suggestion now"),
            BotCommand(command="schedule", description="Manage reminder schedules"),
            BotCommand(command="import", description="Import posting history"),
            BotCommand(command="strategy", description="Add strategy notes"),
            BotCommand(command="settings", description="Tune suggestion settings"),
            BotCommand(command="help", description="Show help"),
        ]
    )
    logger.info("bot_started", webhook_url=settings.webhook_url)


def main() -> None:
    import asyncio

    settings = Settings()

    logging.basicConfig(level=settings.log_level)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
    )

    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    vector_store = VectorStore(settings.chroma_path)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(settings, session_factory)

    # Make shared objects available to handlers via bot data
    dp["settings"] = settings
    dp["vector_store"] = vector_store
    dp["session_factory"] = session_factory

    if settings.webhook_url:
        # Webhook mode
        app = web.Application()

        async def _startup(_app):
            await on_startup(bot, settings, scheduler=None)
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
            )

        async def _shutdown(_app):
            await bot.delete_webhook()
            await engine.dispose()

        app.on_startup.append(_startup)
        app.on_shutdown.append(_shutdown)

        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path="/bot")
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=8080)
    else:
        # Polling mode (local dev)
        async def _run():
            await on_startup(bot, settings, scheduler=None)
            try:
                await dp.start_polling(bot)
            finally:
                await engine.dispose()

        asyncio.run(_run())


if __name__ == "__main__":
    main()
