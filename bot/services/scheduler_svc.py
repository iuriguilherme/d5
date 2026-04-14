"""SchedulerService — domain wrapper around APScheduler lifecycle."""
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bot.models import Reminder

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        session_factory: async_sessionmaker[AsyncSession],
        reminder_fire_fn: Callable[..., Any],
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._fire_fn = reminder_fire_fn

    # ── Job ID convention ─────────────────────────────────────────────────────

    @staticmethod
    def job_id(reminder_id: UUID) -> str:
        return f"reminder_{reminder_id}"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def load_reminders_from_db(self, user_id: int) -> int:
        """Load all active Reminders for user_id and register APScheduler jobs.

        Returns the number of jobs registered.
        """
        async with self._session_factory() as session:
            stmt = select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.active.is_(True),
            )
            reminders = (await session.execute(stmt)).scalars().all()

        count = 0
        for reminder in reminders:
            self._register_job(reminder)
            count += 1

        logger.info("scheduler_loaded_reminders", user_id=user_id, count=count)
        return count

    def _register_job(self, reminder: Reminder) -> None:
        trigger = CronTrigger.from_crontab(
            reminder.schedule_expression,
            timezone=self._scheduler.timezone,
        )
        self._scheduler.add_job(
            self._fire_fn,
            trigger=trigger,
            id=self.job_id(reminder.reminder_id),
            args=[reminder.reminder_id],
            replace_existing=True,
            misfire_grace_time=300,  # 5-minute grace for missed fires
        )

    # ── Domain operations ─────────────────────────────────────────────────────

    async def add_reminder(self, reminder: Reminder) -> None:
        self._register_job(reminder)
        logger.info("scheduler_job_added", job_id=self.job_id(reminder.reminder_id))

    async def remove_reminder(self, reminder_id: UUID) -> None:
        jid = self.job_id(reminder_id)
        job = self._scheduler.get_job(jid)
        if job:
            job.remove()
        logger.info("scheduler_job_removed", job_id=jid)

    async def reschedule_reminder(self, reminder_id: UUID, cron_expr: str) -> None:
        jid = self.job_id(reminder_id)
        trigger = CronTrigger.from_crontab(
            cron_expr, timezone=self._scheduler.timezone
        )
        self._scheduler.reschedule_job(jid, trigger=trigger)
        logger.info("scheduler_job_rescheduled", job_id=jid, cron=cron_expr)
