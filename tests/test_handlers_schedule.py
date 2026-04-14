"""Tests for /schedule handler."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Reminder, User
from bot.models.subject import SubjectSource, SubjectStatus


async def _seed_user(session: AsyncSession, user_id: int) -> User:
    user = User(user_id=user_id)
    session.add(user)
    await session.flush()
    return user


def _make_reminder(
    user_id: int,
    platform: str = "instagram",
    cron: str = "0 9 * * *",
    active: bool = True,
) -> Reminder:
    return Reminder(
        reminder_id=uuid4(),
        user_id=user_id,
        platform=platform,
        schedule_expression=cron,
        active=active,
    )


def _make_message(user_id: int = 1) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = ""
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 1) -> MagicMock:
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(**data) -> MagicMock:
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


def _make_scheduler_svc() -> MagicMock:
    svc = MagicMock()
    svc.add_reminder = AsyncMock()
    svc.remove_reminder = AsyncMock()
    svc.reschedule_reminder = AsyncMock()
    return svc


# ── /schedule (empty) ─────────────────────────────────────────────────────────


async def test_schedule_no_reminders(db_session: AsyncSession):
    from bot.handlers.schedule import cmd_schedule

    await _seed_user(db_session, 80001)
    message = _make_message(user_id=80001)
    await cmd_schedule(message=message, session=db_session)

    message.answer.assert_called_once()
    assert "no reminders" in message.answer.call_args[0][0].lower()


# ── /schedule (with reminders) ────────────────────────────────────────────────


async def test_schedule_shows_reminders(db_session: AsyncSession):
    from bot.handlers.schedule import cmd_schedule

    user_id = 80002
    await _seed_user(db_session, user_id)
    db_session.add(_make_reminder(user_id, "instagram", "0 9 * * *"))
    db_session.add(_make_reminder(user_id, "tiktok", "0 18 * * *"))
    await db_session.commit()

    message = _make_message(user_id=user_id)
    await cmd_schedule(message=message, session=db_session)

    # Header + 2 reminder messages
    assert message.answer.call_count == 3


# ── Edit flow ─────────────────────────────────────────────────────────────────


async def test_sched_edit_sets_state():
    from bot.handlers.schedule import sched_edit

    rid = str(uuid4())
    callback = _make_callback(data=f"sched:edit:{rid}")
    state = _make_state()

    await sched_edit(callback=callback, state=state)

    state.set_state.assert_called_once()
    state.update_data.assert_called_with(reminder_id=rid)
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


async def test_sched_receive_cron_valid_updates_db(db_session: AsyncSession):
    from bot.handlers.schedule import sched_receive_cron

    user_id = 80003
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id, cron="0 9 * * *")
    db_session.add(reminder)
    await db_session.flush()

    message = _make_message(user_id=user_id)
    message.text = "0 18 * * 1-5"
    state = _make_state(reminder_id=str(reminder.reminder_id))
    svc = _make_scheduler_svc()

    await sched_receive_cron(
        message=message,
        state=state,
        session=db_session,
        scheduler_service=svc,
    )

    await db_session.refresh(reminder)
    assert reminder.schedule_expression == "0 18 * * 1-5"
    svc.reschedule_reminder.assert_called_once()
    state.clear.assert_called_once()
    message.answer.assert_called_once()


async def test_sched_receive_cron_invalid_stays_in_state(db_session: AsyncSession):
    from bot.handlers.schedule import sched_receive_cron

    user_id = 80004
    message = _make_message(user_id=user_id)
    message.text = "not a cron"
    state = _make_state(reminder_id=str(uuid4()))
    svc = _make_scheduler_svc()

    await sched_receive_cron(
        message=message,
        state=state,
        session=db_session,
        scheduler_service=svc,
    )

    # Should NOT clear state and NOT reschedule
    state.clear.assert_not_called()
    svc.reschedule_reminder.assert_not_called()
    message.answer.assert_called_once()
    assert "invalid" in message.answer.call_args[0][0].lower()


# ── Pause ─────────────────────────────────────────────────────────────────────


async def test_sched_pause_sets_inactive(db_session: AsyncSession):
    from bot.handlers.schedule import sched_pause

    user_id = 80005
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id, active=True)
    db_session.add(reminder)
    await db_session.flush()

    callback = _make_callback(data=f"sched:pause:{reminder.reminder_id}", user_id=user_id)
    svc = _make_scheduler_svc()

    await sched_pause(callback=callback, session=db_session, scheduler_service=svc)

    await db_session.refresh(reminder)
    assert reminder.active is False
    svc.remove_reminder.assert_called_once_with(reminder.reminder_id)
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called()


# ── Resume ────────────────────────────────────────────────────────────────────


async def test_sched_resume_sets_active(db_session: AsyncSession):
    from bot.handlers.schedule import sched_resume

    user_id = 80006
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id, active=False)
    db_session.add(reminder)
    await db_session.flush()

    callback = _make_callback(data=f"sched:resume:{reminder.reminder_id}", user_id=user_id)
    svc = _make_scheduler_svc()

    await sched_resume(callback=callback, session=db_session, scheduler_service=svc)

    await db_session.refresh(reminder)
    assert reminder.active is True
    svc.add_reminder.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called()


# ── reminder_fire_handler ─────────────────────────────────────────────────────


async def test_fire_handler_sends_suggestion(db_session: AsyncSession):
    from bot.handlers.schedule import reminder_fire_handler
    from bot.models import Subject

    user_id = 80010
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id)
    db_session.add(reminder)

    subject = Subject(
        user_id=user_id,
        text="fire subject",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    db_session.add(subject)
    await db_session.flush()

    # Mock session factory
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)

    mock_engine = MagicMock()
    mock_engine.suggest = AsyncMock(return_value=subject)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    await reminder_fire_handler(
        reminder.reminder_id,
        session_factory=mock_factory,
        suggestion_engine=mock_engine,
        bot=mock_bot,
        user_id=user_id,
    )

    mock_bot.send_message.assert_called_once()
    call_text = mock_bot.send_message.call_args[1].get("text") or mock_bot.send_message.call_args[0][1]
    assert "fire subject" in call_text


async def test_fire_handler_no_subjects_sends_message(db_session: AsyncSession):
    from bot.handlers.schedule import reminder_fire_handler
    from bot.services.suggestion import NoSubjectAvailableError

    user_id = 80011
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id)
    db_session.add(reminder)
    await db_session.flush()

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)

    mock_engine = MagicMock()
    mock_engine.suggest = AsyncMock(side_effect=NoSubjectAvailableError("cooldown"))

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    await reminder_fire_handler(
        reminder.reminder_id,
        session_factory=mock_factory,
        suggestion_engine=mock_engine,
        bot=mock_bot,
        user_id=user_id,
    )

    mock_bot.send_message.assert_called_once()
    msg = mock_bot.send_message.call_args[0][1]
    assert "cooldown" in msg.lower()


# ── sched:skip ────────────────────────────────────────────────────────────────


async def test_sched_skip_creates_post(db_session: AsyncSession):
    from bot.handlers.schedule import sched_skip
    from bot.models import Post, Subject
    from sqlalchemy import select

    user_id = 80020
    await _seed_user(db_session, user_id)
    reminder = _make_reminder(user_id, platform="tiktok")
    db_session.add(reminder)
    subject = Subject(
        user_id=user_id,
        text="skip subject",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    db_session.add(subject)
    await db_session.flush()

    rid = str(reminder.reminder_id)
    sid = str(subject.subject_id)
    callback = _make_callback(data=f"sched:skip:{rid}:{sid}", user_id=user_id)

    await sched_skip(callback=callback, session=db_session)

    posts = (
        await db_session.execute(select(Post).where(Post.user_id == user_id))
    ).scalars().all()
    assert len(posts) == 1
    from bot.models.post import PostSource
    assert posts[0].source == PostSource.skipped
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── sched:another ─────────────────────────────────────────────────────────────


async def test_sched_another_shows_new_suggestion():
    from bot.handlers.schedule import sched_another
    from bot.models import Subject
    from bot.services.suggestion import NoSubjectAvailableError

    subject = Subject(
        user_id=1,
        text="alternative subject",
        source=SubjectSource.manual,
        status=SubjectStatus.active,
    )
    subject.subject_id = uuid4()

    rid = str(uuid4())
    excluded = str(uuid4())
    callback = _make_callback(data=f"sched:another:{rid}:{excluded}", user_id=1)

    mock_engine = MagicMock()
    mock_engine.suggest = AsyncMock(return_value=subject)

    session = MagicMock()

    await sched_another(callback=callback, session=session, suggestion_engine=mock_engine)

    callback.message.edit_text.assert_called_once()
    edit_text = callback.message.edit_text.call_args[0][0]
    assert "alternative subject" in edit_text
    callback.answer.assert_called_once()


async def test_sched_another_no_subjects():
    from bot.handlers.schedule import sched_another
    from bot.services.suggestion import NoSubjectAvailableError

    rid = str(uuid4())
    excluded = str(uuid4())
    callback = _make_callback(data=f"sched:another:{rid}:{excluded}", user_id=1)

    mock_engine = MagicMock()
    mock_engine.suggest = AsyncMock(side_effect=NoSubjectAvailableError("empty"))

    session = MagicMock()

    await sched_another(callback=callback, session=session, suggestion_engine=mock_engine)

    callback.message.edit_text.assert_called_once()
    edit_text = callback.message.edit_text.call_args[0][0]
    assert "available" in edit_text.lower()
