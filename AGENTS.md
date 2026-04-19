# WDWGN — Agent Context

## Project

**WDWGN** ("Where Do We Go Now") — single-user Telegram bot for organizing social media content subjects, tracking posting history, and receiving AI-assisted suggestions. Also called "Social Media Content Organizer" internally.

**License:** GPLv3

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | Aiogram 3.x (asyncio, FSM, InlineKeyboardMarkup) |
| Relational DB | SQLite via aiosqlite + SQLAlchemy 2.x async |
| Migrations | Alembic (async pattern) |
| Vector DB | ChromaDB PersistentClient (SQLite-backed, in-process) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim, local) |
| Clustering | scikit-learn DBSCAN |
| LLM (optional) | OpenAI GPT-4o-mini or Ollama (graceful fallback if unset) |
| Scheduler | APScheduler 3.x asyncio (AsyncIOScheduler + synchronous SQLAlchemyJobStore, jobs stored in SQLite) |
| Config | pydantic-settings v2 + `.env` |
| Logging | Python `logging` + `structlog` (JSON) |
| Deployment | Single Docker container on VPS (webhook or polling) |

## Directory Layout

```
bot/                    ← main Python package
  config.py             ← pydantic-settings Settings class
  main.py               ← entrypoint
  models/               ← SQLAlchemy ORM models
  db/                   ← AsyncEngine + AsyncSession factory
  vector/               ← ChromaDB VectorStore wrapper
  scheduler/            ← APScheduler lifecycle
  handlers/             ← Aiogram routers (one file per command group)
  services/             ← SuggestionEngine, ImportService, PredictionService, SchedulerService
  heuristics/           ← pluggable heuristic callables + HeuristicRegistry
  importers/            ← pluggable platform importers + ImporterRegistry
alembic/                ← Alembic migrations
tests/                  ← pytest-asyncio test suite
docker/                 ← Dockerfile, nginx.conf
docs/
  brainstorms/          ← architecture brainstorm documents
  plans/                ← implementation plans
  solutions/            ← documented solutions to past problems (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (module, tags, problem_type). Relevant when implementing or debugging in documented areas.
```

## Key Architectural Constraints

- **Single-user per deployment.** All DB tables carry `user_id` (Telegram user ID as int PK). Multi-user requires PostgreSQL + ChromaDB server — not implemented.
- **APScheduler starts inside Aiogram's `on_startup` hook.** Never create a new event loop for the scheduler. Share Aiogram's running loop.
- **ChromaDB is synchronous.** All ChromaDB calls must be wrapped in `asyncio.to_thread()`.
- **sentence-transformers is synchronous.** Same — wrap in `asyncio.to_thread()`.
- **SQLite WAL mode must be enabled** at engine creation via `PRAGMA journal_mode=WAL`.
- **LLM is optional.** Bot must function fully without `OPENAI_API_KEY` (clustering-only prediction mode).
- **Webhook mode when `WEBHOOK_URL` set; polling fallback otherwise** (enables local dev without Nginx).
- **Access control via `ALLOWED_USER_IDS`.** Outer Aiogram middleware rejects any user not in `settings.ALLOWED_USER_IDS`; empty list disables the check. Prevents unexpected access since any Telegram user can message a bot.
- **APScheduler 3.x uses synchronous `SQLAlchemyJobStore`.** `AsyncSQLAlchemyJobStore` does not exist in APScheduler 3.x (it is 4.x-only). Use sync `SQLAlchemyJobStore` with `sqlite:///` URL; sync I/O is acceptable at single-user scale.
- **FSM state is SQLite-backed.** `bot/db/fsm_storage.py` implements Aiogram `BaseStorage` over aiosqlite. FSM state survives bot restarts.

## Extensibility Patterns

- **New heuristic:** add file to `bot/heuristics/`, register in `HeuristicRegistry`. No core engine changes.
- **New platform importer:** add file to `bot/importers/`, register in `ImporterRegistry`. No core import flow changes.

## Documentation

Do not delete files under docs/

If files are no longer relevant to the current context, archive them under the appropriate archive/ subfolder of each section.

Every change to the codebase should be documented using the appropriate tool.

### Compound Engineering Workflows

This repository uses Compound Engineering to track decisions and scale knowledge:

- `docs/brainstorms/` — captures product-level requirements and scope decisions using `/ce:brainstorm`. Completed brainstorms should be archived in `docs/brainstorms/archive/`.
- `docs/plans/` — technical implementation plans created using `/ce:plan`. Once implemented and verified, plans should be moved to `docs/plans/archive/`.
- `docs/ideation/` — open-ended notes, research, and deferred feature ideas.

### Documented Solutions

`docs/solutions/` — documented solutions, architecture decisions, and best practices organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas. Create these using `/ce:compound`.

### Prompt Convention

Prompts go in `docs/prompts/`, not `prompts/`.

## Efficiency & Communication

- **Caveman Mode** — use `caveman` skill whenever applicable to minimize token usage and keep communication terse.

## Versioning & Tagging

- **SemVer** — use `vX.Y.Z` prefix for git tags.
- **Rules**:
  - `feat`: increment minor (`v0.Y.0`).
  - `fix`: increment patch (`v0.0.Z`).
  - `refactor`: increment minor if breaking changes, increment patch otherwise.
  - `docs`, `chore`: do NOT tag.
