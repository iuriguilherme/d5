---
title: "feat: Social Media Content Organizer — Telegram Bot"
type: feat
status: active
date: 2026-04-13
origin: docs/brainstorms/social-media-organizer.md
deepened: 2026-04-14
---

# feat: Social Media Content Organizer — Telegram Bot

## Overview

Greenfield Python Telegram bot that helps a single user manage social media content ideas, track posting history, and receive AI-assisted suggestions. All architecture decisions are resolved in the origin document. This plan defines the implementation sequence, file layout, test coverage, and integration boundaries.

## Problem Frame

User needs to organize content subjects for Instagram, TikTok, and Threads across varying posting frequencies without losing ideas, repeating subjects too soon, or losing awareness of their own posting strategy. A Telegram bot is the chosen interface because it is always-on, mobile-native, and requires no separate app install.

(see origin: docs/brainstorms/social-media-organizer.md)

## Requirements Trace

- R1. User can add content subjects via /idea FSM flow (text → confirm → pool)
- R2. Bot sends scheduled reminders with a suggested subject from the pool
- R3. User can record what was actually posted via /posted flow
- R4. Suggestion engine applies a pluggable heuristics pipeline (recency penalty, cooldown, strategy alignment, novelty, platform fit, jitter)
- R5. User can import posting history from Instagram/TikTok/Threads data exports
- R6. Prediction system clusters import history to surface candidate subjects for approval
- R7. User can submit strategy notes; these are embedded and used to weight suggestions
- R8. All reminder schedules are configurable per-platform and mutable at runtime
- R9. Bot works without any LLM API key (clustering-only fallback)
- R10. All data persists across restarts (SQLite + ChromaDB on mounted Docker volume)
- R11. Deployable as single Docker container on a small VPS

## Scope Boundaries

- Single-user per deployment instance (multi-user requires PostgreSQL + ChromaDB server — out of scope)
- No live platform API sync at launch (file-based import only)
- No web UI — Telegram is the only interface
- No training of a custom ranking model (pluggable heuristics pipeline is the ceiling for v1)

### Deferred to Separate Tasks

- API-based sync (Instagram Graph API, TikTok Business API): separate task after launch
- Per-platform cooldown configuration: global default now, per-platform in a future iteration
- Heuristic Profile sharing / export: future iteration
- Multi-user extension (PostgreSQL + ChromaDB server mode): separate task

## Context & Research

### Relevant Code and Patterns

- No existing application code — greenfield
- Project identity: "WDWGN / Where Do We Go Now" (README); code package named `bot/`
- All extensibility patterns defined in origin document: `HeuristicRegistry`, `ImporterRegistry`, `PlatformImporter` Protocol

### Institutional Learnings

- No entries in `docs/solutions/` yet (first build)

### External References

- Aiogram 3 docs: https://docs.aiogram.dev/en/stable/
- APScheduler 3.x docs: https://apscheduler.readthedocs.io/en/3.x/
- ChromaDB docs: https://docs.trychroma.com/
- sentence-transformers: https://www.sbert.net/
- SQLAlchemy 2 async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

## Key Technical Decisions

- **Single-user scope**: simplest viable deployment; user-scoped data model is already in the schema so multi-user is a scaling upgrade not a redesign (see origin §9)
- **LLM optional**: clustering-only mode must work without `OPENAI_API_KEY`; LLM used only for richer cluster labels and on-demand idea generation
- **Global 14-day cooldown default**: per-platform cooldown deferred; configurable via `/settings`
- **APScheduler shares Aiogram event loop**: scheduler initialized inside `on_startup` hook, passed the existing running loop — not creating a new one (critical integration point, see Unit 5)
- **SQLite WAL mode**: enabled via SQLAlchemy `PRAGMA journal_mode=WAL` at engine creation; handles concurrent bot handler reads + APScheduler writes
- **Strategy alignment**: averaged cosine similarity across all strategy note embeddings; switch to top-K if signal degrades with many notes (deferred)
- **DBSCAN defaults**: `epsilon=0.3`, `min_samples=2` — empirically reasonable for 384-dim short-text embeddings; exposed as config for tuning
- **Webhook default, polling fallback**: `WEBHOOK_URL` present → webhook mode; absent → polling (enables local dev without Nginx)
- **Package name**: `bot/` as top-level Python package; Docker image named `wdwgn-bot`
- **Config via pydantic-settings v2**: single `Settings` class loaded from `.env`; all optional fields have safe defaults

## Open Questions

### Resolved During Planning

- **Single vs multi-user**: single-user per instance; `user_id` present on all tables for future upgrade
- **LLM default**: optional; bot functional without it
- **Cooldown**: 14-day global default, configurable
- **APScheduler + Aiogram event loop**: use `on_startup` hook to start scheduler inside running loop
- **WAL mode**: explicit PRAGMA at engine creation
- **DBSCAN hyperparameters**: epsilon=0.3, min_samples=2, both configurable
- **Strategy embedding aggregation**: average for v1, top-K deferred

### Deferred to Implementation

- Exact Telegram file size handling for imports >20MB: implement size check in handler, instruct user to compress or split; fallback mechanism TBD during implementation
- Real platform export format variations: Instagram/TikTok/Threads JSON schemas may differ by account type; importer must handle missing optional fields gracefully — exact field fallbacks discovered during implementation against real samples
- APScheduler `SQLAlchemyJobStore` resolved to use synchronous `sqlite:///` URL (not `sqlite+aiosqlite:///`); job store I/O is sync and acceptable at single-user scale
- Alembic env.py async pattern: confirm `run_migrations_online` uses `AsyncEngine` correctly during Unit 2

## Output Structure

```
wdwgn-bot/                          ← repo root
├── bot/                            ← main Python package
│   ├── __init__.py
│   ├── main.py                     ← entrypoint (bot startup)
│   ├── config.py                   ← pydantic-settings Settings class
│   ├── models/                     ← SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── subject.py
│   │   ├── post.py
│   │   ├── reminder.py
│   │   ├── strategy_note.py
│   │   ├── heuristic_profile.py
│   │   └── import_batch.py
│   ├── db/                         ← database setup
│   │   ├── __init__.py
│   │   ├── engine.py               ← AsyncEngine + WAL pragma
│   │   ├── session.py              ← AsyncSession factory
│   │   └── fsm_storage.py          ← SQLite-backed Aiogram FSM BaseStorage
│   ├── vector/                     ← ChromaDB integration
│   │   ├── __init__.py
│   │   └── client.py               ← PersistentClient + collection helpers
│   ├── scheduler/                  ← APScheduler integration
│   │   ├── __init__.py
│   │   └── setup.py                ← AsyncIOScheduler lifecycle
│   ├── handlers/                   ← Aiogram routers
│   │   ├── __init__.py
│   │   ├── start.py                ← /start, /help
│   │   ├── idea.py                 ← /idea FSM
│   │   ├── posted.py               ← /posted FSM
│   │   ├── pool.py                 ← /pool, /pending
│   │   ├── suggest.py              ← /suggest (on-demand)
│   │   ├── schedule.py             ← /schedule
│   │   ├── import_.py              ← /import + document handler
│   │   ├── strategy.py             ← /strategy
│   │   └── settings.py             ← /settings
│   ├── services/                   ← business logic
│   │   ├── __init__.py
│   │   ├── suggestion.py           ← SuggestionEngine
│   │   ├── import_.py              ← ImportService
│   │   ├── prediction.py           ← PredictionService
│   │   └── scheduler_svc.py        ← SchedulerService
│   ├── heuristics/                 ← pluggable heuristic callables
│   │   ├── __init__.py
│   │   ├── registry.py             ← HeuristicRegistry
│   │   ├── recency.py
│   │   ├── cooldown.py
│   │   ├── strategy_align.py
│   │   ├── novelty.py
│   │   ├── platform_fit.py
│   │   └── jitter.py
│   └── importers/                  ← pluggable platform importers
│       ├── __init__.py
│       ├── registry.py             ← ImporterRegistry
│       ├── base.py                 ← PlatformImporter Protocol + PostRecord
│       ├── instagram.py
│       ├── tiktok.py
│       ├── threads.py
│       └── generic_csv.py
├── alembic/                        ← Alembic migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── conftest.py                 ← async fixtures, in-memory SQLite, mock ChromaDB
│   ├── test_models.py
│   ├── test_suggestion_engine.py
│   ├── test_heuristics.py
│   ├── test_importers.py
│   ├── test_prediction.py
│   ├── test_handlers.py
│   └── test_scheduler_svc.py
├── docker/
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── pyproject.toml                  ← deps, tool config (ruff, pytest, mypy)
├── alembic.ini
└── .env.example
```

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
Telegram ──HTTPS──► Nginx ──► Aiogram webhook server (aiohttp)
                                        │
                              Dispatcher (routers, FSM middleware)
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                  │                    │
              Handlers            APScheduler          Background jobs
              (FSM flows)    (fires reminder jobs)   (prediction, import)
                    │                  │
                    └──────────────────┘
                                   │ calls
                          Application Services
                    ┌──────────────┬──────────────┐
              SuggestionEngine  ImportService  PredictionService
                    │                  │              │
              HeuristicRegistry  ImporterRegistry  EmbeddingPipeline
                    │                  │              │
                    └──────────────────┴──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
              SQLAlchemy async              ChromaDB PersistentClient
              (SQLite WAL)              (subject_embeddings, strategy_embeddings)
```

**Startup sequence:**
1. `alembic upgrade head`
2. Create `AsyncEngine` (SQLite + WAL pragma)
3. Initialize ChromaDB `PersistentClient`
4. Build Aiogram `Dispatcher`, register routers
5. In `on_startup`: start `AsyncIOScheduler`, load reminder jobs from DB
6. Start bot (webhook or polling)

## Implementation Units

---

- [ ] **Unit 1: Project Scaffolding and Configuration**

**Goal:** Create all project boilerplate — package structure, dependency manifest, config layer, and Docker foundation.

**Requirements:** R10, R11

**Dependencies:** None

**Files:**
- Create: `pyproject.toml`
- Create: `bot/__init__.py`, `bot/config.py`
- Create: `bot/models/__init__.py`, `bot/db/__init__.py`, `bot/vector/__init__.py`, `bot/scheduler/__init__.py`, `bot/handlers/__init__.py`, `bot/services/__init__.py`, `bot/heuristics/__init__.py`, `bot/importers/__init__.py`
- Create: `docker/Dockerfile`, `docker-compose.yml`, `.env.example`
- Create: `alembic.ini`
- Test: `tests/conftest.py`

**Approach:**
- `pyproject.toml` uses `[project]` table (PEP 621) with `hatchling` build backend; pin major versions of all deps
- Required runtime packages: `aiogram>=3.0,<4`, `apscheduler>=3.10,<4`, `sqlalchemy[asyncio]>=2.0,<3`, `aiosqlite>=0.19`, `alembic>=1.13`, `chromadb>=0.4`, `sentence-transformers>=2.7`, `scikit-learn>=1.4`, `pydantic-settings>=2.0,<3`, `structlog>=24.0`, `openai>=1.0` (optional), `httpx>=0.27` (Aiogram dep)
- Required dev/test packages: `pytest>=8.0`, `pytest-asyncio>=0.23`, `anyio>=4.0`
- `bot/config.py`: single `Settings(BaseSettings)` class; reads from `.env`; fields: `TELEGRAM_BOT_TOKEN` (required), `ALLOWED_USER_IDS: list[int]` (default `[]` → allowlist disabled, all users permitted; set to one or more Telegram user IDs to restrict access), `WEBHOOK_URL` (optional → polling fallback), `OPENAI_API_KEY` (optional), `OLLAMA_BASE_URL` (optional), `DATA_DIR` (default `/data`), `EMBEDDING_MODEL` (default `all-MiniLM-L6-v2`), `SCHEDULER_TIMEZONE` (default `UTC`), `LOG_LEVEL` (default `INFO`), `DBSCAN_EPSILON` (default `0.3`), `DBSCAN_MIN_SAMPLES` (default `2`), `COOLDOWN_DAYS` (default `14`)
- Dockerfile: multi-stage; builder installs deps; runtime image is slim Python; CMD runs startup script
- `docker-compose.yml`: single service, volume mount for `/data`, reads `.env`
- `tests/conftest.py`: pytest-asyncio fixtures for in-memory SQLite engine, mock ChromaDB client, mock Telegram bot
- `.gitignore`: add `.env` and `.env.*` (except `.env.example`) to prevent accidental secret commit; existing gitignore already covers `*.local.md`

**Patterns to follow:**
- pydantic-settings v2: `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`

**Test scenarios:**
- Happy path: `Settings()` loads from `.env.example` values without error
- Edge case: Missing `TELEGRAM_BOT_TOKEN` raises `ValidationError`
- Edge case: `WEBHOOK_URL` absent → `settings.webhook_url is None` (polling mode signal)
- Happy path: `DATA_DIR` defaults to `/data` when not set

**Verification:**
- `pyproject.toml` installs cleanly in a fresh virtualenv
- `docker-compose build` succeeds
- `Settings()` instantiates with `.env.example` values

---

- [ ] **Unit 2: Database Models and Alembic Migrations**

**Goal:** Define all SQLAlchemy async ORM models and generate the initial Alembic migration.

**Requirements:** R1, R2, R3, R5, R7, R10

**Dependencies:** Unit 1

**Files:**
- Create: `bot/db/engine.py`, `bot/db/session.py`
- Create: `bot/models/base.py`, `bot/models/user.py`, `bot/models/subject.py`, `bot/models/post.py`, `bot/models/reminder.py`, `bot/models/strategy_note.py`, `bot/models/heuristic_profile.py`, `bot/models/import_batch.py`
- Create: `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial_schema.py`
- Test: `tests/test_models.py`

**Approach:**
- `bot/db/engine.py`: creates `AsyncEngine` via `create_async_engine("sqlite+aiosqlite:///...")`, listens for `connect` event to emit `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON`
- `bot/db/session.py`: `async_sessionmaker` factory; expose `get_session()` async context manager
- All models use UUID primary keys (`uuid4` default) except `User` which uses Telegram `user_id` (int) as PK
- `User` model includes `cooldown_days: int` column (default: `settings.COOLDOWN_DAYS`, i.e. 14); settable via `/settings`
- `Subject.source` enum: `manual | ai_predicted`; `Subject.status` enum: `active | pending_approval | archived`
- `Subject.last_posted_at`: nullable datetime; updated by /posted flow and import backfill; used by recency and cooldown heuristics
- `Post.platform` enum: `instagram | tiktok | threads | other`; `Post.source` enum: `manual_confirm | imported | skipped`
- `HeuristicProfile.config` stored as `JSON` column
- `Reminder.schedule_expression` stores cron string; `Reminder.active` bool
- `alembic/env.py`: async migration pattern using `AsyncEngine` — `run_async_migrations()` called via `asyncio.run()` in offline mode; online mode uses `async with engine.begin() as conn: await conn.run_sync(do_run_migrations)`

**Patterns to follow:**
- `DeclarativeBase` with `MappedColumn` type annotations (SQLAlchemy 2 style)
- `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)`

**Test scenarios:**
- Happy path: all models insert and query via async session against in-memory SQLite
- Happy path: `Subject` with `status=pending_approval` queryable separately from `status=active`
- Edge case: FK constraint — `Post` with nonexistent `subject_id` raises `IntegrityError`
- Edge case: `Reminder` with `active=False` excluded from scheduler load query
- Integration: WAL mode PRAGMA fires on engine connect (check `PRAGMA journal_mode` returns `wal`)

**Verification:**
- `alembic upgrade head` runs without error against a fresh SQLite file
- All model instances round-trip through async session (insert → query → compare)

---

- [ ] **Unit 3: ChromaDB Integration Layer**

**Goal:** Wrap ChromaDB `PersistentClient` with typed helpers for subject and strategy collections.

**Requirements:** R4, R6, R7

**Dependencies:** Unit 1

**Files:**
- Create: `bot/vector/client.py`
- Test: `tests/conftest.py` (mock ChromaDB fixture)

**Approach:**
- `VectorStore` class wraps `chromadb.PersistentClient(path=settings.DATA_DIR / "chroma")`
- Two collections per user (created if not exists): `subject_embeddings_{user_id}`, `strategy_embeddings_{user_id}`
- Methods: `upsert_subject(subject_id, embedding, metadata)`, `get_subject_embedding(subject_id)`, `upsert_strategy(note_id, embedding, metadata)`, `query_similar_subjects(embedding, n_results)`, `query_strategy_alignment(subject_embedding, n_results)`
- ChromaDB PersistentClient is synchronous; all calls wrap in `asyncio.to_thread()` to avoid blocking the event loop
- `embedding_id` field on `Subject` and `StrategyNote` models stores the ChromaDB document ID (same as the model's UUID)

**Patterns to follow:**
- `asyncio.to_thread()` pattern for sync I/O in async context

**Test scenarios:**
- Happy path: `upsert_subject` then `get_subject_embedding` returns same vector
- Happy path: `query_similar_subjects` returns nearest neighbors in correct order
- Edge case: querying empty collection returns empty list (not error)
- Integration: `upsert_strategy` then `query_strategy_alignment` returns cosine similarity > 0 for related text

**Verification:**
- `VectorStore` instantiates and all methods run against a temp ChromaDB path in tests

---

- [ ] **Unit 4: Aiogram 3 Bot Setup and Router Architecture**

**Goal:** Build the Aiogram 3 Dispatcher, register all command routers, configure FSM middleware, and wire startup/shutdown hooks.

**Requirements:** R1, R2, R3, R8 (UX shell)

**Dependencies:** Units 1, 2

**Files:**
- Create: `bot/main.py`
- Create: `bot/db/fsm_storage.py`
- Create: `bot/handlers/start.py`
- Test: `tests/test_handlers.py`

**Approach:**
- `bot/main.py` is the entrypoint: creates `Bot`, `Dispatcher`, instantiates services, registers routers, defines `on_startup`/`on_shutdown` hooks, starts webhook or polling based on `settings.webhook_url`
- `Dispatcher` uses `SqliteStorage` backed by the same SQLite DB for FSM state persistence across restarts; implement `bot/db/fsm_storage.py` as a custom `BaseStorage` subclass using aiosqlite, storing FSM state in a `fsm_state` table (columns: `user_id`, `chat_id`, `state`, `data`); this is a project-internal implementation, not a third-party package
- Access control middleware: register an Aiogram outer middleware in `bot/main.py` that reads `message.from_user.id` and rejects updates where `settings.ALLOWED_USER_IDS` is non-empty and `user_id not in settings.ALLOWED_USER_IDS`; replies with "Access denied." and returns early; this ensures no command handler runs for unlisted users
- All routers use `Router()` and are included into the root Dispatcher via `dp.include_router()`
- `bot/handlers/start.py`: handles `/start` (onboarding + default reminder seeding), `/help` (command reference)
- Onboarding in `/start`: creates `User` record if not exists, seeds 4 default `Reminder` records (one per platform) using cron expressions from origin document
- Command menu registered via `BotCommand` list at startup
- Webhook server uses Aiogram's built-in aiohttp `SimpleRequestHandler`; path includes secret token from `WEBHOOK_URL`

**Patterns to follow:**
- Aiogram 3 router composition pattern
- `dp.startup.register(on_startup)` hook pattern

**Test scenarios:**
- Happy path: `/start` for new user creates User record + 4 default Reminder records
- Happy path: `/start` for existing user does not duplicate records
- Happy path: `/help` returns message containing all command names
- Security: update from unlisted user ID when `ALLOWED_USER_IDS` is set → middleware returns "Access denied.", handler not called
- Security: update from any user when `ALLOWED_USER_IDS` is empty → middleware passes through (allowlist disabled)
- Happy path: FSM state written to SQLite `fsm_state` table, survives in-memory loss (confirm by writing state, recreating storage instance, reading state back)
- Integration: dispatcher processes a mocked update without error (smoke test)

**Verification:**
- Bot starts in polling mode against a test bot token
- `/start` flow creates expected DB records
- `fsm_storage.py` round-trips FSM state through real SQLite (not in-memory)

---

- [ ] **Unit 5: APScheduler Integration**

**Goal:** Integrate APScheduler 3.x AsyncIOScheduler with Aiogram 3's event loop; wire reminder jobs to bot message dispatch.

**Requirements:** R2, R8, R10

**Dependencies:** Units 2, 4

**Files:**
- Create: `bot/scheduler/setup.py`
- Create: `bot/services/scheduler_svc.py`
- Test: `tests/test_scheduler_svc.py`

**Approach:**
- `bot/scheduler/setup.py`: creates `AsyncIOScheduler` with synchronous `SQLAlchemyJobStore` (APScheduler 3.x — `AsyncSQLAlchemyJobStore` does not exist in 3.x; it is a 4.x class) pointing at the same SQLite DB via a plain sync URL `sqlite:///path/to/db.sqlite3` (table: `apscheduler_jobs`); job store I/O is synchronous but acceptable at single-user scale; scheduler started inside Aiogram's `on_startup` hook (the event loop is already running)
- `SchedulerService` in `bot/services/scheduler_svc.py`: wraps scheduler with domain methods: `load_reminders_from_db()` (reads all `Reminder` where `active=True`, adds/reschedules APScheduler jobs), `add_reminder(reminder)`, `remove_reminder(reminder_id)`, `reschedule_reminder(reminder_id, cron_expr)`
- Each APScheduler job calls `reminder_fire_handler(reminder_id, bot)` which: queries the `Reminder`, calls `SuggestionEngine.suggest()`, sends Telegram message with inline buttons
- Job ID format: `reminder_{reminder_id}` (matches `Reminder.reminder_id` UUID)

**Technical design:**
- Scheduler must be started *after* the event loop is running. Aiogram's `on_startup` hook runs inside the running loop — safe to call `await scheduler.start()` there
- Do NOT call `asyncio.run(scheduler.start())` — this creates a new loop, conflicts with Aiogram's loop

**Patterns to follow:**
- APScheduler 3.x: `scheduler.add_job(func, CronTrigger.from_crontab(expr), id=job_id, replace_existing=True)`

**Test scenarios:**
- Happy path: `load_reminders_from_db()` with 4 active reminders → 4 APScheduler jobs registered
- Happy path: `reschedule_reminder()` updates the APScheduler job trigger
- Happy path: `remove_reminder()` removes the APScheduler job without error
- Edge case: `load_reminders_from_db()` with no active reminders → 0 jobs, no error
- Integration: reminder fire handler produces a Telegram `send_message` call (mock bot)

**Verification:**
- Scheduler starts and stops cleanly within Aiogram lifecycle in integration test
- Jobs survive simulated bot restart (loaded from SQLite job store)

---

- [ ] **Unit 6: Subject Pool Commands (/idea, /pool, /pending)**

**Goal:** Implement FSM flows for adding subjects, viewing the pool, and approving/rejecting AI-predicted candidates.

**Requirements:** R1, R6

**Dependencies:** Units 2, 4, 11

**Files:**
- Create: `bot/handlers/idea.py`, `bot/handlers/pool.py`
- Test: `tests/test_handlers.py` (extend)

**Approach:**
- `/idea` FSM: `IdeaStates.waiting_for_text` → user sends text → bot confirms with inline `[Save] [Edit] [Cancel]` → on Save: creates `Subject(source=manual, status=active)`, embeds text (calls `PredictionService.embed_text()`), stores in ChromaDB; on Edit: re-prompts; on Cancel: discards
- `/pool` handler: queries `Subject` where `status=active`, renders paginated list (5 per page) with `<< Prev` / `Next >>` inline buttons; page state passed via callback data
- `/pending` handler: queries `Subject` where `status=pending_approval`, renders paginated list with `[Approve] [Reject] [Info]` buttons per entry; Approve → sets `status=active`, updates ChromaDB embedding; Reject → sets `status=archived`
- Inline keyboard callback data uses compact format: `pool:page:{n}`, `pending:approve:{subject_id}`, `pending:reject:{subject_id}`

**Test scenarios:**
- Happy path: `/idea` full FSM flow → Subject record created with `status=active`
- Happy path: User chooses Edit → bot re-prompts, second text accepted
- Happy path: User chooses Cancel → no Subject created
- Happy path: `/pool` with 7 subjects → first page shows 5, Next >> loads page 2
- Happy path: `/pending` approve → subject moves to `status=active`
- Happy path: `/pending` reject → subject moves to `status=archived`
- Edge case: `/pool` with 0 subjects → bot sends "Your pool is empty" message

**Verification:**
- All FSM state transitions tested via mocked dispatcher
- Pool pagination correct for edge cases (0, 1, exactly 5, 6+ subjects)

---

- [ ] **Unit 7: Posting Confirmation Flow (/posted)**

**Goal:** Implement the /posted FSM to record what the user actually posted.

**Requirements:** R3

**Dependencies:** Units 2, 4

**Files:**
- Create: `bot/handlers/posted.py`
- Test: `tests/test_handlers.py` (extend)

**Approach:**
- `/posted` FSM: `PostedStates.waiting_for_subject` → user describes what they posted (free text) → bot shows matching subjects from pool with inline select + "None of these" option → `PostedStates.waiting_for_platform` → user selects platform from inline keyboard → bot confirms → creates `Post(source=manual_confirm)` record; if subject selected, updates `Subject.last_posted_at` (add this field to schema)
- Optional caption: after platform selection, bot asks "Add a caption excerpt? [Skip] [Add]"
- On completion: bot confirms "Logged! ✓ [Subject] posted to [Platform]"
- Semantic subject matching uses ChromaDB `query_similar_subjects()` with the free text; top 3 results shown as inline options

**Test scenarios:**
- Happy path: full flow → Post record created with correct user_id, platform, posted_at
- Happy path: "None of these" → Post created with `subject_id=null`
- Happy path: caption added → stored in `Post.caption_excerpt`
- Happy path: skip caption → `Post.caption_excerpt` is null
- Edge case: empty pool → bot skips subject selection, goes straight to platform

**Verification:**
- Post records created correctly in all flow branches
- Subject matching returns top-3 candidates from ChromaDB

---

- [ ] **Unit 8: Suggestion Engine (Heuristics Pipeline)**

**Goal:** Implement `SuggestionEngine` with the full pluggable heuristics pipeline.

**Requirements:** R4

**Dependencies:** Units 2, 3, 11

**Files:**
- Create: `bot/services/suggestion.py`
- Create: `bot/handlers/suggest.py`
- Create: `bot/heuristics/registry.py`, `bot/heuristics/recency.py`, `bot/heuristics/cooldown.py`, `bot/heuristics/strategy_align.py`, `bot/heuristics/novelty.py`, `bot/heuristics/platform_fit.py`, `bot/heuristics/jitter.py`
- Test: `tests/test_suggestion_engine.py`, `tests/test_heuristics.py`

**Approach:**
- `SuggestionContext` dataclass: `user`, `posting_history`, `now`, `platform_hint`, `strategy_embeddings`, `settings`
- `HeuristicRegistry`: dict mapping name → async callable; `register(name, fn)`, `get_enabled(profile)` returns ordered list from profile config
- Each heuristic: `async def heuristic(subject: Subject, ctx: SuggestionContext) -> float`
- `SuggestionEngine.suggest(user_id, platform_hint)`: loads active subjects, loads profile, scores all subjects via pipeline (summed weighted scores), applies epsilon-greedy (10% chance to pick from top-3 pool randomly), returns selected subject
- Cooldown heuristic: returns `-inf` if `Subject` posted within `settings.COOLDOWN_DAYS`; implemented by checking `Post` history
- Strategy alignment heuristic: averages cosine similarities between subject embedding and all strategy embeddings (uses `VectorStore.query_strategy_alignment()`)
- `/suggest` command handler added to `bot/handlers/suggest.py` as thin wrapper calling `SuggestionEngine.suggest()`

**Test scenarios:**
- Happy path: `suggest()` returns a subject from the active pool
- Happy path: subject within cooldown window excluded from results
- Happy path: subject with high strategy alignment scores higher than low-alignment subject (mock embeddings)
- Happy path: never-posted subject gets novelty bonus
- Edge case: all subjects in cooldown → `suggest()` raises `NoSubjectAvailableError`
- Edge case: epsilon-greedy fires → result is one of top-3, not always top-1
- Happy path: `jitter` heuristic prevents deterministic ties (score varies across calls)
- Integration: full pipeline with 10 subjects + real heuristic weights → deterministic scoring (fixed seed)

**Verification:**
- Each heuristic unit-tested in isolation with mock subjects/context
- Full pipeline integration test produces expected ranking order

---

- [ ] **Unit 9: Reminder System (/schedule)**

**Goal:** Implement the /schedule handler for viewing and modifying reminder schedules; wire reminder fire sequence to SuggestionEngine.

**Requirements:** R2, R8

**Dependencies:** Units 4, 5, 8

**Files:**
- Create: `bot/handlers/schedule.py`
- Test: `tests/test_scheduler_svc.py` (extend)

**Approach:**
- `/schedule` handler: lists current reminders (platform, schedule, status) with inline `[Edit] [Pause] [Resume]` per entry, plus `[Add reminder]` button
- Edit flow FSM: `ScheduleStates.waiting_for_cron` → user sends new cron expression → bot validates (try `CronTrigger.from_crontab(expr)`) → updates `Reminder` record → calls `SchedulerService.reschedule_reminder()`
- Pause/Resume: toggles `Reminder.active`, calls `SchedulerService.remove_reminder()` or `add_reminder()` accordingly
- Reminder fire handler (`reminder_fire_handler`): calls `SuggestionEngine.suggest()` → sends message with subject + `[Post this] [Skip] [Suggest another]` buttons
- `[Post this]` → triggers abbreviated `/posted` FSM (skips subject search, uses suggested subject)
- `[Skip]` → creates `Post(source=skipped, subject_id=suggested_subject_id, platform=reminder.platform)` record (no separate SkipEvent model needed; `Post.source` enum already has `skipped` value), updates `Reminder.last_fired_at`
- `[Suggest another]` → calls `suggest()` again, excludes current suggestion from pool for this session

**Test scenarios:**
- Happy path: `/schedule` shows all 4 default reminders
- Happy path: Edit reminder → cron updated in DB + APScheduler job rescheduled
- Happy path: Pause → `Reminder.active=False`, job removed from scheduler
- Happy path: Resume → `Reminder.active=True`, job re-added
- Error path: invalid cron expression → bot shows error, stays in FSM state
- Error path: all subjects in cooldown → reminder fires → `suggest()` raises `NoSubjectAvailableError` → bot sends user-visible message "All subjects are in cooldown — add new ideas with /idea or reduce cooldown in /settings" (not silence)
- Integration: reminder fires → `SuggestionEngine.suggest()` called → message sent with inline buttons

**Verification:**
- Cron validation rejects invalid expressions with user-visible error
- Pause/resume cycle leaves scheduler in consistent state
- All-subjects-cooldown scenario sends a message (not silent drop)

---

- [ ] **Unit 10: History Import (/import)**

**Goal:** Implement the /import wizard and all platform importers.

**Requirements:** R5

**Dependencies:** Units 2, 3, 4

**Files:**
- Create: `bot/handlers/import_.py`
- Create: `bot/importers/base.py`, `bot/importers/registry.py`
- Create: `bot/importers/instagram.py`, `bot/importers/tiktok.py`, `bot/importers/threads.py`, `bot/importers/generic_csv.py`
- Create: `bot/services/import_.py`
- Test: `tests/test_importers.py`

**Approach:**
- `/import` FSM: platform selection inline keyboard → bot prompts user to send file → `ImportStates.waiting_for_file` → receives Telegram document → size check (>20MB → instruct to compress) → saves to `DATA_DIR/imports/{user_id}/{batch_id}/` → dispatches to `ImportService`
- `PlatformImporter` Protocol (in `base.py`): `platform: str`, `async def detect(file_path: Path) -> bool`, `async def parse(file_path: Path) -> list[PostRecord]`
- `PostRecord` dataclass: `platform`, `posted_at: datetime`, `caption: str | None`
- `ImporterRegistry`: tries `detect()` on each registered importer; first match wins
- Platform-specific parsing (key fields per origin document §5):
  - Instagram: `content/posts_1.json` → `timestamp`, `title`
  - TikTok: `user_data.json` → `Video.Videos.VideoList[].Date`, `Link`
  - Threads: `threads_and_replies/posts.json` → `timestamp`, `text`
  - Generic CSV: `date`, `caption` columns; configurable column mapping
- `ImportService.process(user_id, batch_id, file_path)`: parse → insert `Post` records → create `ImportBatch` record → trigger `PredictionService.cluster_import(user_id, batch_id)`
- File unzipping handled in `ImportService`; raw ZIP stored, extracted to temp dir for parsing

**Test scenarios:**
- Happy path: Instagram ZIP parsed → correct `PostRecord` list with timestamps
- Happy path: TikTok ZIP parsed → correct records
- Happy path: Threads ZIP parsed → correct records
- Happy path: Generic CSV parsed → records with configurable column names
- Edge case: ZIP with unexpected structure → `detect()` returns `False`, falls to generic handler
- Edge case: Missing optional field (e.g., no caption) → `PostRecord.caption=None`, no error
- Error path: file >20MB → bot sends "File too large" message, no import
- Integration: full import flow → `Post` records in DB + `ImportBatch` record created

**Verification:**
- Each importer tested against fixture ZIP/JSON files with known content
- Import summary message shows correct record count

---

- [ ] **Unit 11: Prediction System (Embedding + Clustering)**

**Goal:** Implement PredictionService — embedding pipeline, DBSCAN clustering, gap topic detection, pending approval queue population.

**Requirements:** R6, R9

**Dependencies:** Units 2, 3

**Files:**
- Create: `bot/services/prediction.py`
- Test: `tests/test_prediction.py`

**Approach:**
- `PredictionService.__init__`: eagerly loads `SentenceTransformer(settings.EMBEDDING_MODEL)` at construction time (not lazily on first call); model loading takes 2–10s on a small VPS — doing it at startup avoids cold-start latency on the first `/suggest` or reminder fire
- `PredictionService.embed_text(text: str) -> list[float]`: uses the already-loaded model instance; calls `model.encode([text], normalize_embeddings=True)[0]`; wraps in `asyncio.to_thread()` (sentence-transformers is synchronous)
- `PredictionService.cluster_import(user_id, batch_id)`: fetches `Post` records from this batch, embeds captions in batches, runs `DBSCAN(eps=settings.DBSCAN_EPSILON, min_samples=settings.DBSCAN_MIN_SAMPLES, metric='cosine')` — explicit `metric='cosine'` required because `epsilon=0.3` is calibrated in cosine-distance space (cosine_distance=0.3 ≈ 73% similarity); the sklearn default of `'euclidean'` would interpret epsilon=0.3 as Euclidean distance producing far tighter clusters than intended, finds cluster centroids, queries ChromaDB for nearest subject per centroid, flags clusters with no close match (`cosine_distance > 0.5`) as gap topics, creates `Subject(source=ai_predicted, status=pending_approval)` records for gap topics, notifies user via bot message
- Gap topic label: use the most representative sentence in the cluster (nearest to centroid) as the subject text; optionally enrich via LLM if `OPENAI_API_KEY` set
- LLM enrichment (optional): instantiate `AsyncOpenAI(api_key=settings.OPENAI_API_KEY)` and call `await client.chat.completions.create(...)` — use the openai v1 SDK async interface (`openai.ChatCompletion` was removed in openai SDK v1.0); falls back to raw sentence if API unavailable or key not set
- Embedding batch size: 32 (configurable); avoids OOM on small VPS

**Test scenarios:**
- Happy path: `embed_text("my cooking video")` returns list of 384 floats, norm ≈ 1.0
- Happy path: `cluster_import()` with 10 posts → DBSCAN produces at least 1 cluster → at least 1 pending_approval subject created (mock ChromaDB shows no close match)
- Happy path: cluster with existing subject in pool → no duplicate pending_approval created (cosine_distance < 0.5)
- Edge case: all posts have empty/null captions → no subjects created, no error
- Edge case: fewer posts than `min_samples` → DBSCAN labels all as noise → no subjects created
- Integration: `embed_text()` + `upsert_subject()` → `query_similar_subjects()` returns correct nearest neighbor

**Verification:**
- Embedding output is unit-normalized (L2 norm ≈ 1.0 within float tolerance)
- Clustering produces no duplicate pending_approval subjects for already-covered topics

---

- [ ] **Unit 12: Strategy Notes (/strategy)**

**Goal:** Implement the /strategy command to accept strategy research text, embed it, and store it for use in suggestion weighting.

**Requirements:** R7

**Dependencies:** Units 2, 3, 11

**Files:**
- Create: `bot/handlers/strategy.py`
- Test: `tests/test_handlers.py` (extend)

**Approach:**
- `/strategy` FSM: `StrategyStates.waiting_for_text` → user sends text → bot confirms → creates `StrategyNote` record → calls `PredictionService.embed_text()` → stores embedding in `strategy_embeddings_{user_id}` ChromaDB collection → no recompute triggered (strategy alignment is computed lazily at suggestion time by the `strategy_align` heuristic)
- No `Subject.strategy_weight` denorm column — cosine alignment is computed at suggestion time in `strategy_align` heuristic via `VectorStore.query_strategy_alignment()`; this eliminates the O(N×M) recompute-on-save bottleneck and keeps the Subject schema simpler
- Bot confirms with "Strategy note saved. Suggestions will now reflect this strategy."

**Test scenarios:**
- Happy path: `/strategy` full flow → `StrategyNote` in DB + embedding in ChromaDB
- Edge case: very long text (>1000 chars) → accepted, no truncation (embedding handles)
- Integration: strategy note affects suggestion ranking in `SuggestionEngine` (higher cosine → higher strategy_align score, verified via mock embeddings in Unit 8 tests)

**Verification:**
- `StrategyNote` created and embedding retrievable from ChromaDB
- No `Subject.strategy_weight` column in schema (omit from `alembic/versions/0001_initial_schema.py`)

---

- [ ] **Unit 13: Settings and Onboarding Polish (/settings)**

**Goal:** Implement /settings command for heuristic weight tuning and user preference management.

**Requirements:** R4 (weight configurability)

**Dependencies:** Units 2, 4, 8

**Files:**
- Create: `bot/handlers/settings.py`
- Test: `tests/test_handlers.py` (extend)

**Approach:**
- `/settings` shows current heuristic profile weights with inline keyboard: each heuristic listed with `[Low] [Medium] [High] [Off]` buttons (current value highlighted)
- Tapping a weight button: updates `HeuristicProfile.config` JSON, confirms "Updated [heuristic] weight to [level]"
- Additional settings: `[Set cooldown days]` → FSM to enter integer → validates range 1–365 → stored in `User.cooldown_days` column (add to User model in Unit 2); this is a per-user global setting, not per-profile
- Default `HeuristicProfile` seeded during `/start` onboarding (Unit 4) with all heuristics at Medium weight

**Test scenarios:**
- Happy path: `/settings` shows all 6 heuristics with current weights
- Happy path: tap `[High]` on recency → `HeuristicProfile.config` updated
- Happy path: set cooldown to 7 → `cooldown_days` stored, affects heuristic
- Edge case: cooldown input "abc" → validation error, bot re-prompts

**Verification:**
- Weight changes persist across bot restarts (stored in DB)
- Updated weights reflected in next `SuggestionEngine.suggest()` call

---

- [ ] **Unit 14: Docker, Nginx, and Production Deployment**

**Goal:** Complete Docker and Nginx configuration for VPS deployment in webhook mode.

**Requirements:** R11

**Dependencies:** All previous units

**Files:**
- Modify: `docker/Dockerfile`
- Create: `docker/nginx.conf`
- Modify: `docker-compose.yml`

**Approach:**
- `Dockerfile`: final stage uses `python:3.12-slim`; copies only `bot/` and `pyproject.toml`; runs `pip install --no-cache-dir .`; entrypoint runs `alembic upgrade head && python -m bot.main`
- `docker-compose.yml`: bot service + optional Nginx service (only in webhook mode); `/data` volume declared; `depends_on` for startup order
- `docker/nginx.conf`: reverse proxy to `bot:8080`; SSL termination via Let's Encrypt certbot (certbot invoked separately, not in compose)
- `docker-compose.yml` exposes port 8080 internally only when behind Nginx; exposes 8443 in polling-only mode

**Test scenarios:**
- Test expectation: none — deployment config is not unit-testable; verified by Docker build + VPS smoke test

**Verification:**
- `docker compose build` succeeds
- `docker compose up` starts bot in polling mode (no Nginx, no WEBHOOK_URL set)
- Webhook registration confirmed via Telegram API response

---

## System-Wide Impact

- **Interaction graph:** APScheduler jobs call `SuggestionEngine` and then `Bot.send_message()` — these cross service → scheduler → bot boundaries; all must share the same `AsyncSession` factory and `VectorStore` instance
- **Error propagation:** APScheduler job failures must be caught and logged; unhandled exceptions inside a job do not kill the scheduler but silently drop the reminder — add `misfire_grace_time` and explicit try/except in `reminder_fire_handler`
- **State lifecycle risks:** ChromaDB `embedding_id` on Subject must be kept in sync with actual ChromaDB documents — if Subject is archived, its ChromaDB document should be deleted or filtered at query time; document deletion not required for v1 (query filters on `status=active`)
- **API surface parity:** all inline keyboard callbacks must be handled by the same router that sent them — register callback handlers in the same handler file as the message that generated the keyboard
- **Integration coverage:** reminder fire → suggest → message → user action (post/skip/swap) is the core loop; this requires end-to-end integration testing with mock scheduler job execution
- **Unchanged invariants:** Telegram `user_id` (int) is the auth token and user identity — never expose or accept external auth; all DB operations are scoped by `user_id` from `message.from_user.id`

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| APScheduler 3.x `SQLAlchemyJobStore` sync in async context | Job store I/O is sync (acceptable at single-user scale); use `MemoryJobStore` during unit tests to avoid SQLite contention |
| Platform export JSON schema varies by account type / export date | Importer `parse()` must treat all non-timestamp fields as optional; log unrecognized schema for debugging |
| sentence-transformers 80MB model download on first run delays startup | Download model in Dockerfile build stage; bake into image |
| Telegram 20MB file size limit blocks large exports | Size check before download attempt; user instructed to compress; document this in `/help` |
| ChromaDB PersistentClient blocking calls in async context | All ChromaDB calls wrapped in `asyncio.to_thread()`; if latency becomes issue, consider thread pool executor |
| DBSCAN produces no clusters on sparse history (<5 posts) | Guard in `cluster_import()`: skip clustering if post count < `min_samples`; notify user to import more history |
| SQLite write contention under concurrent bot handler + APScheduler | WAL mode mitigates; single-user scale means this is unlikely to surface; monitor if scaling |

## Documentation / Operational Notes

- `.env.example` must document all env vars with comments explaining optional vs required
- `/help` command should mention the 20MB import file size limit
- Backup strategy: copy `/data/` directory (SQLite file + ChromaDB directory) — document in README
- Model download: `all-MiniLM-L6-v2` baked into Docker image to avoid runtime download delay
- Let's Encrypt renewal via `certbot renew` cron on host (outside Docker scope)
- AGENTS.md is already populated; keep it updated as the project evolves (stack changes, new constraints)

## Sources & References

- **Origin document:** [docs/brainstorms/social-media-organizer.md](docs/brainstorms/social-media-organizer.md)
- Aiogram 3: https://docs.aiogram.dev/en/stable/
- APScheduler 3.x: https://apscheduler.readthedocs.io/en/3.x/
- ChromaDB: https://docs.trychroma.com/
- sentence-transformers: https://www.sbert.net/
- SQLAlchemy 2 async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- pydantic-settings v2: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Alembic async: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
