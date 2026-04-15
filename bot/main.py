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
from bot.handlers import (
    idea,
    import_,
    pool,
    posted,
    schedule,
    settings as settings_handler,
    start,
    strategy,
    suggest,
)
from bot.scheduler.setup import build_scheduler
from bot.services.import_ import ImportService, build_default_registry
from bot.services.prediction import PredictionService
from bot.services.scheduler_svc import SchedulerService
from bot.services.suggestion import SuggestionEngine
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

    # Register routers — order matters: more specific handlers first
    dp.include_router(start.router)
    dp.include_router(idea.router)
    dp.include_router(pool.router)
    dp.include_router(posted.router)
    dp.include_router(schedule.router)
    dp.include_router(settings_handler.router)
    dp.include_router(strategy.router)
    dp.include_router(suggest.router)
    dp.include_router(import_.router)

    return dp


async def on_startup(
    bot: Bot,
    settings: Settings,
    scheduler_svc: SchedulerService,
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

    # Start APScheduler inside the running event loop
    scheduler_svc._scheduler.start()

    # Load persisted reminders for all configured user IDs
    for user_id in settings.allowed_user_ids:
        await scheduler_svc.load_reminders_from_db(user_id)

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

    # Build services
    prediction_service = PredictionService(settings=settings, vector_store=vector_store)
    suggestion_engine = SuggestionEngine(
        settings=settings,
        session_factory=session_factory,
        vector_store=vector_store,
    )
    import_registry = build_default_registry()
    import_service = ImportService(
        registry=import_registry,
        session_factory=session_factory,
        prediction_service=prediction_service,
        data_dir=settings.data_dir,
    )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Closure that APScheduler calls with only reminder_id; it resolves
    # user_id from the DB and then delegates to the full handler.
    async def _fire_reminder(reminder_id) -> None:
        from bot.models import Reminder as _Reminder

        async with session_factory() as _s:
            _r = await _s.get(_Reminder, reminder_id)
            if _r is None:
                return
            _uid = _r.user_id
        await schedule.reminder_fire_handler(
            reminder_id,
            session_factory=session_factory,
            suggestion_engine=suggestion_engine,
            bot=bot,
            user_id=_uid,
        )

    scheduler = build_scheduler(settings)
    scheduler_svc = SchedulerService(
        scheduler=scheduler,
        session_factory=session_factory,
        reminder_fire_fn=_fire_reminder,
    )

    dp = build_dispatcher(settings, session_factory)

    # Make shared objects available to handlers via dispatcher data.
    # Keys must match handler function parameter names exactly.
    dp["settings"] = settings
    dp["vector_store"] = vector_store
    dp["session_factory"] = session_factory
    dp["prediction_service"] = prediction_service
    dp["suggestion_engine"] = suggestion_engine
    dp["import_service"] = import_service
    dp["scheduler_service"] = scheduler_svc  # handlers use "scheduler_service"
    dp["bot"] = bot

    if settings.webhook_url:
        # Webhook mode
        app = web.Application()

        async def _startup(_app):
            await on_startup(bot, settings, scheduler_svc)
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
            )

        async def _shutdown(_app):
            scheduler.shutdown(wait=False)
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
            await on_startup(bot, settings, scheduler_svc)
            try:
                await dp.start_polling(bot)
            finally:
                scheduler.shutdown(wait=False)
                await engine.dispose()

        asyncio.run(_run())


if __name__ == "__main__":
    main()
