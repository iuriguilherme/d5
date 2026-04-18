---
title: Aiogram Dispatcher Wiring Gaps and APScheduler Integration
date: 2026-04-14
category: docs/solutions/integration-issues/
module: bot
problem_type: integration_issue
component: service_object
severity: critical
symptoms:
  - All commands except /start silently ignored every user message
  - Handlers expecting injected services received nothing and would raise at runtime
  - '"Post this" inline button taps were silently dropped with no response'
  - Background cluster import exceptions were swallowed with no logging or propagation
  - ZIP extraction allowed path traversal outside the designated extract directory
root_cause: missing_association
resolution_type: code_fix
related_components:
  - background_job
  - authentication
  - database
tags:
  - aiogram
  - dependency-injection
  - router-registration
  - apscheduler
  - service-wiring
  - path-traversal
  - asyncio
  - telegram-bot
---

# Aiogram Dispatcher Wiring Gaps and APScheduler Integration

## Problem

A fully implemented Aiogram 3.x bot had all handlers written and all routers defined, but the dispatcher only registered one router (`start.router`) out of nine. Additionally, no application services were instantiated or injected into the dispatcher's data store, and APScheduler was never started. The bot would respond to `/start` only; all other commands were silently ignored.

## Symptoms

- All commands other than `/start` produced no response from the bot.
- No error was raised at startup — Aiogram does not warn about missing routers.
- Scheduler-fired reminders never delivered; no exception was logged.
- Handler parameters typed as service classes (e.g., `scheduler_service: SchedulerService`) received `None` at runtime, causing `AttributeError` on first method call.
- `sched:post:` inline button taps produced no response (no `BadRequest` either — just silence).

## What Didn't Work

- Searching handler files for errors: all handler code was correct; the fault was entirely in `main.py` wiring.
- Checking Aiogram router registration logs: there are none by default; Aiogram does not log which routers are included.
- Adding routers without injecting services: the bot responded to commands but immediately crashed on any service method call, with `AttributeError: 'NoneType' object has no attribute '...'`, because `dp.data` returned `None` for unregistered keys.
- Injecting services under a mismatched key (`dp["scheduler_svc"]` when the handler parameter was named `scheduler_service`): Aiogram resolved the parameter to `None` without raising any error at startup or dispatch time.

## Solution

### 1. Register all routers in `build_dispatcher()`

```python
from bot.handlers import (
    start, idea, pool, posted, schedule,
    settings_handler, strategy, suggest, import_,
)

def build_dispatcher(settings: Settings, session_factory: async_sessionmaker) -> Dispatcher:
    db_path = str(settings.data_dir / "wdwgn.db")
    storage = SqliteStorage(db_path=db_path)
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(AllowlistMiddleware(settings.allowed_user_ids))
    dp.update.middleware(SessionMiddleware(session_factory))

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
```

Every router that defines command or callback handlers must appear here. There is no auto-discovery; omission is silent.

### 2. Instantiate and inject all services in `main()`

```python
def main() -> None:
    settings = Settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    vector_store = VectorStore(settings.chroma_path)
    bot = Bot(token=settings.telegram_bot_token, ...)

    prediction_service = PredictionService(settings=settings, vector_store=vector_store)
    suggestion_engine = SuggestionEngine(
        settings=settings,
        session_factory=session_factory,
        vector_store=vector_store,
    )
    import_service = ImportService(
        registry=build_default_registry(),
        session_factory=session_factory,
        prediction_service=prediction_service,
        data_dir=settings.data_dir,
    )
    scheduler = build_scheduler(settings)

    # Closure: APScheduler calls fire_fn(reminder_id) with one arg.
    # Captures injected deps; resolves user_id from DB at fire time.
    async def _fire_reminder(reminder_id) -> None:
        async with session_factory() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is None:
                return
            user_id = reminder.user_id
        await schedule.reminder_fire_handler(
            reminder_id,
            session_factory=session_factory,
            suggestion_engine=suggestion_engine,
            bot=bot,
            user_id=user_id,
        )

    scheduler_svc = SchedulerService(
        scheduler=scheduler,
        session_factory=session_factory,
        reminder_fire_fn=_fire_reminder,
    )

    dp = build_dispatcher(settings, session_factory)

    # Keys MUST exactly match handler parameter names
    dp["settings"] = settings
    dp["vector_store"] = vector_store
    dp["session_factory"] = session_factory
    dp["prediction_service"] = prediction_service
    dp["suggestion_engine"] = suggestion_engine
    dp["import_service"] = import_service
    dp["scheduler_service"] = scheduler_svc  # matches: scheduler_service: SchedulerService
    dp["bot"] = bot
```

### 3. Start APScheduler inside Aiogram's `on_startup` hook

```python
async def on_startup(bot: Bot, settings: Settings, scheduler_svc: SchedulerService) -> None:
    scheduler_svc._scheduler.start()
    for user_id in settings.allowed_user_ids:
        await scheduler_svc.load_reminders_from_db(user_id)
    ...
```

Never create a new event loop for the scheduler. APScheduler must share Aiogram's running loop, guaranteed when started inside `on_startup`.

### 4. Add the missing `sched:post:` callback handler

`_suggestion_keyboard()` generated buttons with `callback_data=f"sched:post:{rid}:{subject_id}"`, but no handler consumed that prefix. Every inline button's `callback_data` prefix must have a registered handler:

```python
@router.callback_query(F.data.startswith("sched:post:"))
async def sched_post(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Great! Use /posted to log what you posted.")
    await callback.answer()
```

Without `callback.answer()`, Telegram shows a loading spinner indefinitely.

### 5. Fix `asyncio.create_task` exception swallowing

Background tasks created with `create_task` discard exceptions unless explicitly handled:

```python
# Before — exceptions silently discarded:
asyncio.create_task(self._prediction.cluster_import(...))

# After — named callback with walrus operator avoids calling t.exception() twice:
def _on_cluster_done(t: asyncio.Task) -> None:
    if not t.cancelled() and (exc := t.exception()) is not None:
        logger.error("cluster_import_failed", error=str(exc))

task = asyncio.create_task(self._prediction.cluster_import(...))
task.add_done_callback(_on_cluster_done)
```

Avoid the lambda form: `lambda t: logger.error(...) if not t.cancelled() and t.exception() is not None else None` calls `t.exception()` twice. Use a named function with a walrus operator to capture the exception once.

### 6. Fix ZIP path traversal vulnerability

```python
# Before — unsafe: a crafted zip member like ../../etc/passwd extracts outside extract_dir:
with zipfile.ZipFile(file_path) as zf:
    zf.extractall(extract_dir)

# After — use Path.is_relative_to() (Python 3.9+), not str.startswith:
# str.startswith is bypassable: /tmp/abc123-evil starts with /tmp/abc123
safe_root = extract_dir.resolve()
with zipfile.ZipFile(file_path) as zf:
    for member in zf.namelist():
        member_path = (extract_dir / member).resolve()
        if not member_path.is_relative_to(safe_root):
            raise ValueError(f"Unsafe ZIP member path: {member!r}")
    zf.extractall(extract_dir)
```

### 7. Fix `file_size` falsy check

```python
# Before — size=0 bypasses the guard (0 is falsy):
if doc.file_size and doc.file_size > MAX_FILE_BYTES:

# After — explicit None check:
if doc.file_size is not None and doc.file_size > MAX_FILE_BYTES:
```

### 8. Fix `datetime.utcnow` deprecation (Python 3.12+)

```python
# Before — deprecated and returns a naive datetime:
imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# After — timezone-aware, not deprecated:
from datetime import datetime, timezone

imported_at: Mapped[datetime] = mapped_column(
    DateTime, default=lambda: datetime.now(timezone.utc)
)
```

## Why This Works

**Router registration:** Aiogram's `Dispatcher` is itself a `Router`. `include_router()` adds the child router's filters and handlers to the dispatcher's update processing tree. Omitted routers do not exist in the tree; no error is raised because an empty handler set is valid.

**DI key matching:** Aiogram resolves handler parameters by inspecting the function signature with `inspect.signature()` and looking up each parameter name in `dp.data`. The lookup is a plain dict key access: if the key is absent, the parameter receives `None` (for optional/defaulted params) or raises `TypeError` if required with no default. A mismatched key causes silent `None` injection followed by `AttributeError` at the first method call.

**APScheduler closure:** APScheduler serializes the job function and its `args` to SQLite at registration time. At fire time it calls `fire_fn(*args)` with exactly the stored arguments. Dependencies that are not serializable (`session_factory`, `bot`, `suggestion_engine`) cannot be stored as job args. The closure pattern captures them in Python's lexical scope (not serialized) and resolves runtime-only values (like `user_id`) from the database at fire time.

**`on_startup` hook:** Aiogram's `on_startup` signal fires after the event loop is running and before polling or webhook acceptance begins. Starting APScheduler here ensures it shares the same event loop. Starting it before `asyncio.run()` creates a loop conflict; starting it in a separate thread breaks `async def` job functions.

## Prevention

- **Enumerate routers explicitly.** Keep a single list of all routers at the top of `main.py`. A comment like `# 9 routers total` makes accidental omission visible in code review.
- **Audit `dp.data` keys against handler signatures.** Grep for all handler parameters typed as application services and verify a matching `dp["key"] = ...` exists in `main()`. The key must be the exact Python identifier used as the parameter name.
- **Never `asyncio.create_task` without a `done_callback`** for background work where failures must be observable. Prefer structured logging callbacks or task supervisors.
- **Use `is not None` for all numeric Telegram fields** (`file_size`, `width`, `height`). Zero is a valid value and evaluates falsy.
- **Use `datetime.now(timezone.utc)` throughout.** A `ruff` `DTZ` rule flags `datetime.utcnow()` at lint time.
- **Validate ZIP members before extraction** in any user-supplied file handler. Consider a shared utility `safe_extractall(zf, dest)` to enforce this consistently.
- **Audit inline keyboard callback_data prefixes** against registered handlers. Every prefix generated by a keyboard builder must have a corresponding `@router.callback_query(F.data.startswith(...))` handler.

## Related Issues

- `docs/plans/2026-04-13-001-feat-social-media-organizer-telegram-bot-plan.md` — Unit 4 (dispatcher setup) and Unit 5 (APScheduler) describe intended correct behavior; this doc covers the failure modes discovered during review.
- `docs/brainstorms/social-media-organizer.md` §3 — Corrected in commits `1145eb4` and `c716381`; previously referenced `AsyncSQLAlchemyJobStore` which does not exist in APScheduler 3.x.
- `docs/solutions/documentation-gaps/apscheduler-3x-no-async-sqlalchemy-job-store-2026-04-18.md` — Dedicated knowledge-track doc on the APScheduler 3.x/4.x job store API split (`SQLAlchemyJobStore` sync vs `AsyncSQLAlchemyJobStore` 4.x-only).
