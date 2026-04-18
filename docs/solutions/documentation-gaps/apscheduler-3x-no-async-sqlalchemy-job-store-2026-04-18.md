---
title: "APScheduler 3.x Does Not Have AsyncSQLAlchemyJobStore — Use SQLAlchemyJobStore"
date: 2026-04-18
category: docs/solutions/documentation-gaps/
module: bot/scheduler
problem_type: documentation_gap
component: background_job
severity: high
root_cause: wrong_api
resolution_type: documentation_update
applies_when:
  - Using APScheduler 3.x with asyncio (aiogram, FastAPI, aiohttp, etc.)
  - Persistent job storage is required (jobs survive restarts)
  - SQLite is the backing database (single-user / single-process)
symptoms:
  - Architecture or planning docs reference AsyncSQLAlchemyJobStore as a valid APScheduler 3.x class
  - ImportError at startup when code imports AsyncSQLAlchemyJobStore
  - Silent failure when sqlite+aiosqlite:// URL is passed to the synchronous SQLAlchemyJobStore
tags:
  - apscheduler
  - asyncio
  - job-store
  - sqlite
  - scheduler
  - python
  - version-mismatch
---

# APScheduler 3.x Does Not Have AsyncSQLAlchemyJobStore — Use SQLAlchemyJobStore

## Context

During development of the WDWGN Telegram bot, the initial brainstorm document (session history: Apr 4 session) specified the scheduler architecture as:

> "Jobs are stored in SQLite via `AsyncSQLAlchemyJobStore`, surviving restarts."
> "Recommended Approach: `APScheduler` with `AsyncIOScheduler`, backed by `AsyncSQLAlchemyJobStore`."

This class does **not** exist in APScheduler 3.x. It was introduced in APScheduler 4.x as part of a breaking rewrite of the persistence API. The confusion arises because:

1. Both versions share the `apscheduler` package name on PyPI
2. APScheduler 4.x documentation appears alongside 3.x in search results
3. The 4.x async-native API is attractive to asyncio developers, making `AsyncSQLAlchemyJobStore` a natural-sounding assumption

A separate research session (session history: Apr 7) investigated APScheduler 4.x specifically and surfaced the 3.x/4.x API split clearly — but when the project's architecture was downscoped from multi-user (APScheduler 4.x + PostgreSQL) to single-user (APScheduler 3.x + SQLite), no equivalent version-specific research was done for 3.x. The mismatch was discovered during implementation, not planning.

## Guidance

**In APScheduler 3.x, use `SQLAlchemyJobStore` (synchronous) with a plain `sqlite:///` URL. Use `AsyncIOScheduler` as the scheduler class.**

The job store being synchronous does not prevent running async job functions. `AsyncIOScheduler` handles async jobs natively — only the persistence layer (reading/writing job records to SQLite) is synchronous, which is acceptable at single-user scale.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    # Use settings.db_url_sync (plain sqlite:/// URL — NOT sqlite+aiosqlite://)
    # tablename isolates APScheduler rows from other tables in the same DB file
    job_store = SQLAlchemyJobStore(url=settings.db_url_sync, tablename="apscheduler_jobs")
    return AsyncIOScheduler(
        jobstores={"default": job_store},
        timezone=settings.scheduler_timezone,
    )
```

Start the scheduler inside Aiogram's `on_startup` hook to share the already-running event loop:

```python
async def on_startup(bot: Bot) -> None:
    scheduler.start()
```

Never call `scheduler.start()` before `asyncio.run()` — this creates a separate event loop and causes silent job-dispatch failures in async job functions.

## Why This Matters

`AsyncSQLAlchemyJobStore` does not exist in APScheduler 3.x. Importing it raises `ImportError` at bot startup — a hard crash before the bot can respond to any Telegram message. There is no graceful fallback.

Using `sqlite+aiosqlite://` as the URL with the synchronous `SQLAlchemyJobStore` also fails: the sync store requires a synchronous DBAPI driver. APScheduler 3.x calls `create_all` during `scheduler.start()`, so this error surfaces at startup (not at first job write as you might expect) — raising `sqlalchemy.exc.InvalidRequestError` or a driver-level exception before the bot accepts any Telegram message.

Both mistakes are silent during unit tests that mock the scheduler, so failure surfaces at integration or deployment time only.

## When to Apply

- Project targets APScheduler **3.x** — verify with `pip show apscheduler` (version `3.x.y`)
- Application uses asyncio (Aiogram, FastAPI, aiohttp, or any async framework)
- Persistent job storage over SQLite is needed

This guidance does **not** apply to APScheduler 4.x, which provides `AsyncSQLAlchemyJobStore` and an entirely different configuration API (`AsyncScheduler` + `SQLAlchemyDataStore`).

## Examples

### Incorrect (APScheduler 3.x — both variants fail at runtime)

```python
# Variant A: class does not exist → ImportError at startup
from apscheduler.jobstores.sqlalchemy import AsyncSQLAlchemyJobStore  # ImportError

scheduler = AsyncIOScheduler(
    jobstores={"default": AsyncSQLAlchemyJobStore(url="sqlite+aiosqlite:///jobs.db")},
)

# Variant B: wrong URL driver for sync store → driver error at first job write
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url="sqlite+aiosqlite:///jobs.db")},
)
```

### Correct (APScheduler 3.x)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# Sync URL with sync store — correct combination for APScheduler 3.x
scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url="sqlite:///jobs.db")},
    timezone="UTC",
)

# Start inside on_startup to share Aiogram's running event loop
async def on_startup(bot: Bot) -> None:
    scheduler.start()  # scheduler captured from enclosing scope
```

### Checking your APScheduler version

```bash
pip show apscheduler
# Version: 3.10.4  → use SQLAlchemyJobStore (sync)
# Version: 4.0.0   → use AsyncSQLAlchemyJobStore / SQLAlchemyDataStore (async)
```

### APScheduler 4.x reference (for comparison)

APScheduler 4.x uses an entirely different API: `AsyncScheduler` (not `AsyncIOScheduler`) and `SQLAlchemyDataStore` (not a "job store"). Import paths changed between 4.x point releases — check the [4.x docs](https://apscheduler.readthedocs.io/en/4.x/) rather than copying from 3.x examples.

## Related

- `docs/solutions/integration-issues/missing-router-and-service-wiring-2026-04-14.md` — broader APScheduler/Aiogram wiring context; §3 covers starting APScheduler inside `on_startup` and the event loop sharing requirement
- `docs/plans/2026-04-13-001-feat-social-media-organizer-telegram-bot-plan.md` Unit 5 — plan-level specification that correctly documents `SQLAlchemyJobStore` (sync)
- `docs/brainstorms/social-media-organizer.md` §3 — corrected in commits `1145eb4` (body text) and the follow-up fix (tech-stack table row + open question §7)
