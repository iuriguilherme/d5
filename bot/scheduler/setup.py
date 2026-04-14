"""APScheduler 3.x integration.

AsyncIOScheduler is used so jobs run in the existing event loop.
SQLAlchemyJobStore (synchronous) persists jobs in the same SQLite DB.

IMPORTANT: APScheduler 3.x does not have AsyncSQLAlchemyJobStore — that is a
4.x class. Use the synchronous SQLAlchemyJobStore with a plain sqlite:// URL.
The sync I/O is acceptable at single-user scale.
"""
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import Settings


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Build the AsyncIOScheduler.

    Do NOT call scheduler.start() here — start it inside Aiogram's on_startup
    hook, where the event loop is already running.
    """
    job_store = SQLAlchemyJobStore(url=settings.db_url_sync, tablename="apscheduler_jobs")
    scheduler = AsyncIOScheduler(
        jobstores={"default": job_store},
        timezone=settings.scheduler_timezone,
    )
    return scheduler
