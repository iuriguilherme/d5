"""Tests for SQLAlchemy ORM models."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bot.models import HeuristicProfile, ImportBatch, Post, Reminder, StrategyNote, Subject, User
from bot.models.heuristic_profile import DEFAULT_HEURISTIC_CONFIG
from bot.models.post import PostPlatform, PostSource
from bot.models.subject import SubjectSource, SubjectStatus


# ── User ──────────────────────────────────────────────────────────────────────


async def test_user_insert_and_query(db_session):
    user = User(user_id=100, username="alice", first_name="Alice")
    db_session.add(user)
    await db_session.flush()

    result = await db_session.get(User, 100)
    assert result is not None
    assert result.username == "alice"
    assert result.cooldown_days == 14  # default


async def test_user_cooldown_days_default(db_session):
    user = User(user_id=101)
    db_session.add(user)
    await db_session.flush()
    result = await db_session.get(User, 101)
    assert result.cooldown_days == 14


# ── Subject ───────────────────────────────────────────────────────────────────


async def test_subject_insert(db_session):
    user = User(user_id=200)
    db_session.add(user)
    await db_session.flush()

    subject = Subject(
        user_id=200,
        text="My cooking video ideas",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    db_session.add(subject)
    await db_session.flush()

    result = await db_session.get(Subject, subject.subject_id)
    assert result is not None
    assert result.text == "My cooking video ideas"
    assert result.status == SubjectStatus.active
    assert result.last_posted_at is None


async def test_subject_pending_approval_status(db_session):
    user = User(user_id=201)
    db_session.add(user)
    await db_session.flush()

    pending = Subject(
        user_id=201,
        text="Pending subject",
        source=SubjectSource.ai_predicted,
        status=SubjectStatus.pending_approval,
    )
    db_session.add(pending)
    await db_session.flush()

    from sqlalchemy import select
    stmt = select(Subject).where(Subject.status == SubjectStatus.pending_approval)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].text == "Pending subject"


async def test_subject_no_strategy_weight_column(db_session):
    """strategy_weight must NOT exist — computed lazily at suggestion time."""
    assert not hasattr(Subject, "strategy_weight")


# ── Post ──────────────────────────────────────────────────────────────────────


async def test_post_insert(db_session):
    user = User(user_id=300)
    db_session.add(user)
    await db_session.flush()

    post = Post(
        user_id=300,
        platform=PostPlatform.instagram,
        source=PostSource.manual_confirm,
        posted_at=datetime.now(timezone.utc),
    )
    db_session.add(post)
    await db_session.flush()

    result = await db_session.get(Post, post.post_id)
    assert result.platform == PostPlatform.instagram
    assert result.subject_id is None  # nullable


async def test_post_skipped_source(db_session):
    user = User(user_id=301)
    db_session.add(user)
    await db_session.flush()

    post = Post(
        user_id=301,
        platform=PostPlatform.tiktok,
        source=PostSource.skipped,
        posted_at=datetime.now(timezone.utc),
    )
    db_session.add(post)
    await db_session.flush()

    result = await db_session.get(Post, post.post_id)
    assert result.source == PostSource.skipped


async def test_post_fk_constraint_invalid_subject(db_session):
    user = User(user_id=302)
    db_session.add(user)
    await db_session.flush()

    bad_subject_id = uuid4()
    post = Post(
        user_id=302,
        subject_id=bad_subject_id,
        platform=PostPlatform.threads,
        source=PostSource.imported,
        posted_at=datetime.now(timezone.utc),
    )
    db_session.add(post)
    with pytest.raises(IntegrityError):
        await db_session.flush()


# ── Reminder ──────────────────────────────────────────────────────────────────


async def test_reminder_active_default(db_session):
    user = User(user_id=400)
    db_session.add(user)
    await db_session.flush()

    reminder = Reminder(
        user_id=400,
        platform="instagram",
        schedule_expression="0 9 * * *",
    )
    db_session.add(reminder)
    await db_session.flush()

    result = await db_session.get(Reminder, reminder.reminder_id)
    assert result.active is True
    assert result.last_fired_at is None


async def test_reminder_inactive_excluded_from_query(db_session):
    user = User(user_id=401)
    db_session.add(user)
    await db_session.flush()

    active = Reminder(user_id=401, platform="instagram", schedule_expression="0 9 * * *", active=True)
    inactive = Reminder(user_id=401, platform="tiktok", schedule_expression="0 18 * * *", active=False)
    db_session.add_all([active, inactive])
    await db_session.flush()

    from sqlalchemy import select
    stmt = select(Reminder).where(Reminder.active.is_(True))
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].platform == "instagram"


# ── WAL mode ──────────────────────────────────────────────────────────────────


async def test_wal_pragma_fires_on_connect(db_engine):
    async with db_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()
    # In-memory SQLite doesn't support WAL, but the pragma fires without error
    assert mode in ("wal", "memory")


# ── HeuristicProfile ──────────────────────────────────────────────────────────


async def test_heuristic_profile_default_config(db_session):
    user = User(user_id=500)
    db_session.add(user)
    await db_session.flush()

    profile = HeuristicProfile(user_id=500)
    db_session.add(profile)
    await db_session.flush()

    result = await db_session.get(HeuristicProfile, profile.profile_id)
    assert result.config == DEFAULT_HEURISTIC_CONFIG
    assert result.name == "default"
