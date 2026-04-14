"""Tests for SchedulerService."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.models import Reminder
from bot.services.scheduler_svc import SchedulerService


@pytest.fixture
async def scheduler():
    """In-memory AsyncIOScheduler — started inside the running event loop."""
    sched = AsyncIOScheduler()
    sched.start()  # must be called from within a running event loop (async fixture)
    yield sched
    if sched.running:
        sched.shutdown(wait=False)


@pytest.fixture
def fire_fn():
    return AsyncMock()


@pytest.fixture
def svc(scheduler, fire_fn, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = MagicMock(spec=async_sessionmaker)
    return SchedulerService(
        scheduler=scheduler,
        session_factory=factory,
        reminder_fire_fn=fire_fn,
    )


def _reminder(user_id: int = 1, cron: str = "0 9 * * *", active: bool = True) -> Reminder:
    return Reminder(
        reminder_id=uuid4(),
        user_id=user_id,
        platform="instagram",
        schedule_expression=cron,
        active=active,
    )


# ── load_reminders_from_db ────────────────────────────────────────────────────


async def test_load_reminders_registers_jobs(svc, db_session):
    """4 active reminders → 4 APScheduler jobs."""
    reminders = [_reminder(cron=f"0 {h} * * *") for h in [9, 12, 15, 18]]

    async def _fake_session_factory():
        class _CM:
            async def __aenter__(self_inner):
                return db_session
            async def __aexit__(self_inner, *args):
                pass
        return _CM()

    # Patch session_factory to return our test session
    from sqlalchemy import insert
    from bot.models import User
    db_session.add(User(user_id=1))
    await db_session.flush()
    for r in reminders:
        db_session.add(r)
    await db_session.flush()

    with patch.object(svc, "_session_factory") as mock_factory:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        count = await svc.load_reminders_from_db(user_id=1)

    assert count == 4
    jobs = svc._scheduler.get_jobs()
    assert len(jobs) == 4


async def test_load_reminders_no_active_returns_zero(svc):
    """No active reminders → 0 jobs, no error."""
    with patch.object(svc, "_session_factory") as mock_factory:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock(
            execute=AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        ))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        count = await svc.load_reminders_from_db(user_id=99)

    assert count == 0


# ── add / remove / reschedule ─────────────────────────────────────────────────


async def test_add_reminder_registers_job(svc):
    r = _reminder()
    await svc.add_reminder(r)
    assert svc._scheduler.get_job(svc.job_id(r.reminder_id)) is not None


async def test_remove_reminder_removes_job(svc):
    r = _reminder()
    await svc.add_reminder(r)
    await svc.remove_reminder(r.reminder_id)
    assert svc._scheduler.get_job(svc.job_id(r.reminder_id)) is None


async def test_remove_nonexistent_reminder_no_error(svc):
    """remove_reminder on unknown ID should not raise."""
    await svc.remove_reminder(uuid4())


async def test_reschedule_reminder_updates_trigger(svc):
    r = _reminder(cron="0 9 * * *")
    await svc.add_reminder(r)
    await svc.reschedule_reminder(r.reminder_id, "0 18 * * *")

    job = svc._scheduler.get_job(svc.job_id(r.reminder_id))
    assert job is not None
    # Trigger field expression changes — verify job still exists with new cron
    assert "18" in str(job.trigger)
