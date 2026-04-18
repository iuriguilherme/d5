# Social Media Content Organizer — Telegram Bot

**Brainstorm Date:** 2026-04-04
**Scope:** Full architecture and design — covers 9 dimensions

---

## Executive Summary

- **Python + Aiogram 3** is the recommended bot framework: fully async, built-in FSM, active maintenance (v3.26.0 released March 2026), and the best Python ecosystem fit for LLM/AI integration via `sentence-transformers`, `openai`, and `langchain`.
- **SQLite** handles all structured relational data (subjects, posts, reminders, users, strategy notes) — zero-infrastructure, single-file, perfect for a single-user personal tool.
- **ChromaDB** (persistent mode, SQLite-backed) handles all vector embeddings — installs via `pip`, no separate server, Python-native, ideal for this scale.
- **APScheduler** (asyncio-native, integrated into the bot process) manages the cron reminder system — lightweight, dynamic schedule mutation at runtime, no Redis or broker required.
- The suggestion engine is a pluggable heuristics pipeline: random baseline → recency penalty → strategy-note weight → ML-predicted candidates (user-approved before entering pool), with weights combinable additively and each heuristic swappable as a strategy pattern.

---

## 1. Bot UX and Conversation Flows

### Options Considered

**Option A — Command-only interface**
All interactions are `/commands`. Simple, discoverable via `/help`. Brittle for multi-step flows.

**Option B — Pure inline keyboard menus**
Every action is a button press from a menu tree. Familiar to non-technical users. Poor for free-text input (subject ideas, strategy notes).

**Option C — Hybrid: commands + inline keyboards + FSM for free-text flows (Recommended)**
Commands trigger top-level actions; inline keyboards handle confirmations and selection choices; FSM collects multi-part user input (e.g., idea submission, reminder configuration). Telegram's native UX patterns are respected throughout.

### Recommended Approach

Hybrid model using Aiogram 3's FSM (`StatesGroup`) for multi-step conversations, inline keyboards (`InlineKeyboardMarkup`) for binary confirmations and candidate approval, and a persistent command menu registered via `BotCommand`.

### Command Map

```
/start          — Welcome, onboarding, show main menu
/idea           — Begin FSM flow: enter a new subject idea
/suggest        — Get today's suggested subject (on demand)
/posted         — FSM flow: confirm what you actually posted (subject + optional caption)
/schedule       — View or change reminder schedule
/import         — Import posting history (guided wizard)
/strategy       — Submit strategy notes / research text
/pool           — View the current subject pool (paginated inline)
/pending        — Review AI-predicted subjects awaiting approval
/help           — Command reference
/settings       — User preferences (platform defaults, heuristic weights)
```

### Key Conversation Flows

```
                       ┌──────────────────────────────────────┐
                       │            User Sends /idea          │
                       └──────────────────┬───────────────────┘
                                          │
                              Bot: "What's your idea?"
                                          │
                              User: types free text
                                          │
                       Bot: "Save this idea?" [Yes] [Edit] [Cancel]
                                          │
                          ┌──────────────┼──────────────┐
                         Yes            Edit           Cancel
                          │              │               │
                   Saved to pool    Re-prompt        Discarded
```

```
                       ┌──────────────────────────────────────┐
                       │         Reminder fires (cron)        │
                       └──────────────────┬───────────────────┘
                                          │
                         Bot selects subject via heuristics
                                          │
              Bot: "Time to post! Suggested: [Subject X]
                   [Post this] [Skip] [Suggest another]"
                                          │
                  ┌───────────────────────┼──────────────────┐
               Post this               Skip              Suggest another
                  │                      │                    │
        /posted flow triggers      Logged as skipped   New subject drawn
```

```
                       ┌──────────────────────────────────────┐
                       │          /pending — AI approvals     │
                       └──────────────────┬───────────────────┘
                                          │
                     Bot lists predicted subjects (paginated)
                     Each entry: [Approve] [Reject] [More info]
                                          │
                          Approve → enters active pool
                          Reject  → discarded, noted for model
```

### Inline Pagination

Subject pool and pending approvals use Telegram's `InlineKeyboardMarkup` with page navigation buttons (`<< Prev` / `Next >>`). Maximum 5 items per page to keep messages readable.

### Rationale

FSM is the correct tool for capturing multi-field inputs (idea text, platform tag, reminder time). Inline keyboards keep the bot feeling app-like. Registered `BotCommand` ensures discoverability in the Telegram command picker. All confirmations require explicit user action — no silent auto-adds.

---

## 2. Data Model

### Entities

**User**
- `user_id` (Telegram user ID, primary key)
- `username`
- `timezone`
- `created_at`
- `active_heuristic_profile` (FK to HeuristicProfile)

**Subject**
- `subject_id` (UUID)
- `user_id` (FK)
- `text` (the idea text)
- `source` (`manual` | `ai_predicted`)
- `status` (`active` | `pending_approval` | `archived`)
- `tags` (comma-separated or JSON array — platform hints, topics)
- `strategy_weight` (float, 0.0–1.0, computed from strategy embeddings)
- `created_at`
- `approved_at` (null if pending)
- `embedding_id` (reference into ChromaDB collection)

**Post** (records what was actually posted)
- `post_id` (UUID)
- `user_id` (FK)
- `subject_id` (FK, nullable — may post outside the pool)
- `platform` (`instagram` | `tiktok` | `threads` | `other`)
- `posted_at` (datetime)
- `caption_excerpt` (optional, short text)
- `source` (`manual_confirm` | `imported`)

**Reminder**
- `reminder_id` (UUID)
- `user_id` (FK)
- `schedule_expression` (cron string, e.g., `0 9 * * 1,4`)
- `platform_hint` (which platform this reminder is for)
- `active` (bool)
- `last_fired_at`
- `next_fire_at`

**StrategyNote**
- `note_id` (UUID)
- `user_id` (FK)
- `text` (raw strategy / research text)
- `created_at`
- `embedding_id` (reference into ChromaDB collection)

**HeuristicProfile**
- `profile_id` (UUID)
- `user_id` (FK)
- `name`
- `config` (JSON blob — heuristic weights and enabled plugins)

**ImportBatch**
- `batch_id` (UUID)
- `user_id` (FK)
- `platform`
- `imported_at`
- `record_count`
- `raw_file_path` (relative path to stored plain-text export file)

### Vector Collections (ChromaDB)

Two collections per user:

| Collection | Contents | Used For |
|---|---|---|
| `subject_embeddings` | Embeddings of each Subject.text | Semantic deduplication, similarity search for suggestion |
| `strategy_embeddings` | Embeddings of each StrategyNote.text | Weighting subjects that align with stated strategy |

### Storage: Two-Layer Design

| Layer | Technology | Stores |
|---|---|---|
| Relational | SQLite (via SQLAlchemy async) | Users, Subjects, Posts, Reminders, StrategyNotes, HeuristicProfiles, ImportBatches |
| Vector | ChromaDB persistent | Subject and StrategyNote embeddings |

Raw imported files (JSON exports, CSV) are stored as plain text in a local `data/imports/` directory and referenced by `ImportBatch.raw_file_path`.

### Rationale

SQLite needs zero infrastructure and stores all structured data in a single file — perfect for a single-user personal tool deployed on a VPS. ChromaDB is SQLite-backed internally and runs as an in-process library, adding zero additional services. The two-layer design cleanly separates structured queries (recency, status, FK joins) from semantic similarity queries (strategy alignment, deduplication).

---

## 3. Scheduler Design

### Options Considered

**Option A — OS-level cron (system crontab)**
Simplest possible approach. Fires a script at scheduled times. Pros: zero Python dependencies. Cons: cannot be modified dynamically from the bot without shell access; schedule is per-instance not per-user; no runtime mutation.

**Option B — Celery Beat**
Full distributed task queue with a separate beat scheduler. Pros: scales to many users, persists jobs in a broker. Cons: requires Redis or RabbitMQ — heavyweight for a single-user bot; adds two new services to deploy.

**Option C — APScheduler (asyncio-native, in-process) (Recommended)**
Runs inside the same async event loop as the Aiogram bot. Jobs are stored in SQLite via `SQLAlchemyJobStore` (synchronous), surviving restarts. Supports cron, interval, and one-shot triggers. Can add/modify/remove jobs at runtime through the bot conversation.

### Recommended Approach

`APScheduler` with `AsyncIOScheduler`, backed by `SQLAlchemyJobStore` (synchronous, `sqlite:///` URL) writing to the same SQLite database (separate `apscheduler_jobs` table). Note: `AsyncSQLAlchemyJobStore` does not exist in APScheduler 3.x — that is a 4.x-only class. Each active `Reminder` record maps 1:1 to an APScheduler job keyed by `reminder_id`.

When a user changes their schedule via `/schedule`, the bot:
1. Updates the `Reminder` record in SQLite.
2. Calls `scheduler.reschedule_job(reminder_id, trigger=new_cron_trigger)`.

### Default Platform Frequencies (Seeded at Onboarding)

| Platform | Default Schedule | Cron Expression |
|---|---|---|
| Instagram | 3x/week | `0 9 * * 1,3,5` |
| TikTok | 5x/week | `0 18 * * 1,2,3,4,5` |
| Threads | Daily | `0 10 * * *` |
| Generic | 2x/week | `0 9 * * 2,5` |

These are seeded as default `Reminder` records during `/start` onboarding. The user can override via `/schedule`.

### Reminder Fire Sequence

1. APScheduler fires job for `reminder_id`.
2. Handler calls the suggestion engine to select a subject.
3. Bot sends message to user's `chat_id` with subject + inline action buttons.
4. User action (post/skip/swap) is recorded.
5. `Reminder.last_fired_at` updated; APScheduler auto-computes `next_fire_at`.

### Rationale

APScheduler asyncio mode runs inside the bot process — one deployment artifact, one process, no broker. SQLite job store ensures reminders survive bot restarts. Dynamic rescheduling from inside the bot conversation is a first-class feature. For a single-user application this is the right level of complexity.

---

## 4. Suggestion Engine

### Options Considered

**Option A — Pure random selection**
Draw uniformly at random from the active subject pool. Pros: trivial to implement, zero bias. Cons: may repeat subjects shortly after posting; ignores strategy weighting entirely.

**Option B — Rule-based scoring (Recommended baseline)**
Assign a composite score to each active subject using a configurable pipeline of scoring functions. Each function produces a score delta that is additively combined. Subject with the highest composite score is selected (with configurable epsilon-greedy exploration to avoid determinism).

**Option C — Full ML ranking model**
Train a ranking model on historical data. Pros: potentially highest accuracy. Cons: requires enough history to generalize, adds training complexity, overkill for early-stage single-user deployment.

### Recommended Approach: Pluggable Heuristics Pipeline

Each heuristic is a Python callable with a fixed signature:

```python
async def heuristic(
    subject: Subject,
    context: SuggestionContext,
) -> float:  # score delta, can be negative
    ...
```

`SuggestionContext` carries: posting history, current datetime, active strategy notes, user settings.

### Default Heuristic Stack (ordered by application)

| # | Heuristic | Logic | Weight |
|---|---|---|---|
| 1 | Recency penalty | Subtract score proportional to `1 / days_since_last_post` | High |
| 2 | Cooldown hard block | Score = -∞ if posted within `cooldown_days` (default: 14) | Blocking |
| 3 | Strategy alignment | Cosine similarity between subject embedding and strategy embeddings (averaged), scaled to [0, 1] | Configurable |
| 4 | Novelty bonus | Boost subjects never posted before | Low-medium |
| 5 | Platform fit | Boost subjects tagged for the reminder's target platform | Low |
| 6 | Random jitter | Small uniform noise to prevent deterministic ties | Always-on |

### Weight Combination

```
final_score(subject) = sum(heuristic_i(subject, ctx) * weight_i)
```

Weights live in `HeuristicProfile.config`. The user can adjust weights via `/settings` → "Tune suggestions". The bot exposes this as a series of inline slider-style buttons (Low / Medium / High / Off for each heuristic).

### Pluggability

New heuristics are registered by adding a new Python module in `bot/heuristics/` that exports the callable. A `HeuristicRegistry` singleton maps name strings to callables. `HeuristicProfile.config` stores enabled heuristic names and their weights as JSON. This allows adding a new heuristic without touching core selection logic.

### Epsilon-Greedy Exploration

With configurable probability `epsilon` (default: 0.1), the engine selects a random subject from the top-3 pool rather than always the highest scorer. This prevents the suggestion loop from collapsing to a single repeated subject.

### Rationale

The pluggable pipeline is the sweet spot between simplicity and extensibility. The scoring approach is fully auditable (the user can see why a subject was suggested), requires no training data to bootstrap, and is trivially upgradeable to ML-based ranking by adding one more heuristic that calls a model.

---

## 5. History Import

### Options Considered

**Option A — Official platform APIs only**
Pull posting history via Instagram Graph API, TikTok Business API, Threads API. Pros: live data, future sync possible. Cons: all three require OAuth app approval; Instagram requires Business/Creator accounts; TikTok Business API requires developer approval and is rate-limited; Threads API is nascent.

**Option B — Manual file upload (data export packages)**
All major platforms allow users to download their data archive (GDPR-mandated). These ZIP files contain JSON exports of post history. Pros: works for all platforms, no OAuth, no API keys. Cons: one-shot import, not live sync; user must manually download and share the file via Telegram.

**Option C — Hybrid: file upload first, API sync as optional extension (Recommended)**
Launch with file upload (Option B) as the primary import mechanism. Design the importer as a platform-adapter interface so API connectors can be added later.

### Recommended Approach

Users send their platform data export (ZIP or JSON file) to the bot as a Telegram document message. The bot:
1. Receives the file via Aiogram's document handler.
2. Saves raw file to `data/imports/{user_id}/{batch_id}/`.
3. Dispatches to the appropriate `PlatformImporter` based on file structure detection.
4. Parses post records (title/caption, timestamp, platform).
5. Inserts parsed records as `Post` rows with `source=imported`.
6. Reports import summary to user.

### Platform Data Export Formats

| Platform | Export Format | Key Fields Available |
|---|---|---|
| Instagram | ZIP → `content/posts_1.json` | `timestamp`, `title`, `media_type` |
| TikTok | ZIP → `user_data.json` → `Video.Videos.VideoList` | `Date`, `Link`, `Likes` |
| Threads | ZIP → `threads_and_replies/posts.json` | `timestamp`, `text` |
| Generic CSV | CSV with `date`, `caption` columns | Configurable column mapping |

### Importer Interface

```python
class PlatformImporter(Protocol):
    platform: str

    async def detect(self, file_path: Path) -> bool: ...
    async def parse(self, file_path: Path) -> list[PostRecord]: ...
```

Importers registered in a `ImporterRegistry`, selected by detection. New platform importers are added as new classes without touching core logic.

### Post-Import Processing

After import, the system:
1. Clusters imported post captions semantically (using ChromaDB similarity) to surface candidate subject topics.
2. Presents clusters to the user as pending-approval subjects (`status=pending_approval`).
3. User approves/rejects via `/pending`.

### Rationale

File-based import is universally available, platform-agnostic, and avoids OAuth complexity at launch. The adapter pattern ensures API connectors can be added later. Semantic clustering of import data is where the prediction system feeds back into the subject pool.

---

## 6. Prediction System

### Options Considered

**Option A — Frequency-based topic extraction**
Count word/phrase frequencies in posted content. Cheap, interpretable, no ML. Misses semantic synonyms; brittle to vocabulary variation.

**Option B — Embedding-based clustering (Recommended for initial system)**
Use sentence-transformer embeddings of past post captions/titles. Cluster with K-Means or DBSCAN. Cluster centroids represent recurring themes. Gaps in recent clusters surface as new candidate subjects.

**Option C — Sequence-aware next-post predictor**
Train a sequence model (LSTM or fine-tuned small LLM) on the temporal sequence of posts to predict what type of content fits next. High value if enough history exists (100+ posts), but overkill for bootstrapping.

**Option D — LLM-guided topic suggestion**
Send posting history summary to an LLM (OpenAI GPT-4o or local model via Ollama) and ask it to suggest new subjects. Pros: conversational, high quality suggestions. Cons: API cost, latency, requires prompt engineering. Fits well as an optional "generate new ideas" feature on demand.

### Recommended Approach: Two-Phase Prediction

**Phase 1 — Clustering (always-on):**
After each import or every N new `Post` records:
1. Embed all post captions using `sentence-transformers/all-MiniLM-L6-v2` (local, free, 80MB).
2. Cluster embeddings with DBSCAN (no need to pre-specify K; handles noise).
3. For each cluster, find the centroid's nearest subject in the current pool.
4. Flag clusters with no close match (cosine distance > 0.5 threshold) as "gap topics."
5. Generate a short label for each gap cluster (using the most representative sentence as the label, or optionally an LLM call).
6. Push gap topics to `pending_approval` queue.

**Phase 2 — On-demand LLM enrichment (optional, user-triggered):**
User sends `/pending suggest` or presses "Generate more ideas" button. System sends a structured prompt with the user's last 20 posts and 5 strategy notes to an LLM. LLM returns 5 subject ideas. These enter the `pending_approval` queue. **User must approve before they enter the active pool.**

### Model Choice

| Component | Technology | Rationale |
|---|---|---|
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, fast, runs locally, 80MB, excellent semantic quality |
| Clustering | scikit-learn DBSCAN | No K needed, handles outliers, small scale |
| LLM suggestions | OpenAI GPT-4o-mini (default) or Ollama (local) | Configurable via env var; GPT-4o-mini is cheap (~$0.001/call) |

### Scale Considerations

At single-user scale, the number of posts is unlikely to exceed a few thousand. DBSCAN on 384-dim embeddings for 2000 vectors runs in under 1 second on a small VPS. No GPU required.

### Approval Gate

All AI-predicted subjects carry `status=pending_approval`. They are not presented as suggestions until the user explicitly approves them via `/pending`. This is a hard gate — the system never auto-promotes predicted subjects.

### Rationale

Embedding-based clustering is the right first step: it surfaces real patterns from actual posting history without requiring training data beyond what the user provides. The LLM enrichment layer adds the "personal content coach" quality without making it a dependency — the system works without any API keys. Keeping the approval gate preserves user trust and control.

---

## 7. Tech Stack

### Telegram Bot Framework Research

| Framework | Language | Async | FSM | LLM Ecosystem | Maintenance | Notes |
|---|---|---|---|---|---|---|
| **Aiogram 3** | Python | Native asyncio | Built-in `StatesGroup` | Excellent (all Python AI libs) | Active (v3.26, Mar 2026) | Recommended |
| python-telegram-bot v20+ | Python | asyncio (v20+) | Via `ConversationHandler` | Excellent | Active | Solid alternative; FSM less ergonomic than Aiogram |
| Telegraf | Node.js | Native | Via sessions | Good (JS AI libs) | Active | Best non-Python option; worse AI ecosystem fit |
| grammY | Node.js/Deno | Native | Plugin-based | Good | Active | Modern, lightweight; same AI ecosystem limitation as Telegraf |
| telebot (go-telegram-bot-api) | Go | goroutines | Manual | Poor (no native AI libs) | Active | Best raw performance; poor AI integration |
| Telethon | Python | asyncio | Manual | Excellent | Active | MTProto, not Bot API; for user-bots, not bots |

**Verdict:** Aiogram 3 wins clearly for this use case. The primary maintainer knows it, it has the best Python AI ecosystem fit, built-in FSM, and is actively maintained. No alternative offers a meaningful enough advantage to justify a rewrite or learning curve.

**Go trade-off (honest assessment):** Go would offer 3-10x lower memory usage and faster cold starts, but lacks native libraries for sentence-transformers, scikit-learn clustering, and LLM SDKs. Implementing the AI pipeline in Go would require calling external Python services — adding complexity that negates the simplicity benefit.

### Vector Database Research

| Database | Setup | Python API | Persistence | Scale Ceiling | Notes |
|---|---|---|---|---|---|
| **ChromaDB** | `pip install chromadb` | Native | SQLite-backed file | ~10M vectors on VPS | Recommended |
| Qdrant | Docker or pip (embedded mode) | Native | File or server | Very high | Excellent for large scale; slight overkill at this scale |
| pgvector | PostgreSQL extension | via psycopg2 | PostgreSQL file | High | Best if already on Postgres; adds infra here |
| Weaviate | Docker | Native | Server | High | Too heavy for single-user embedded use |
| FAISS | `pip install faiss-cpu` | Native | Manual serialization | Very high | No metadata filtering; no persistence abstraction |

**Verdict:** ChromaDB for this use case. It installs via pip, persists to disk without a separate server, has a Python-native API, supports metadata filtering, and handles millions of vectors on a small VPS. Qdrant embedded mode is a valid alternative if more sophisticated filtering is needed later.

### Plain Text / Relational Database Research

| Database | Setup | Concurrency | Python ORM | Notes |
|---|---|---|---|---|
| **SQLite** | Built into Python | Single-writer (fine for single user) | SQLAlchemy async | Recommended |
| PostgreSQL | Server install | Multi-writer | SQLAlchemy async | Overkill for single-user; adds infra |
| TinyDB | `pip install tinydb` | Single-process | Direct | Too limited for relational queries |

**Verdict:** SQLite via SQLAlchemy's async engine (`aiosqlite`). Zero infrastructure, single file, full SQL, excellent async support, and APScheduler also stores its jobs there. If the application ever needs multi-user or multi-process access, migrating to PostgreSQL is a one-line SQLAlchemy change.

### Final Recommended Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Bot framework | Aiogram | 3.x (latest: 3.26 as of Mar 2026) |
| Async runtime | asyncio + aiohttp | Built into Aiogram |
| Relational DB | SQLite via aiosqlite + SQLAlchemy async | Single file |
| Vector DB | ChromaDB persistent client | SQLite-backed, in-process |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Local, free, 384-dim |
| Clustering | scikit-learn DBSCAN | CPU-only, fast at this scale |
| LLM (optional) | OpenAI GPT-4o-mini or Ollama | Configurable via env; graceful fallback if unset |
| Scheduler | APScheduler 3.x asyncio | Jobs stored in same SQLite DB via SQLAlchemyJobStore (synchronous) |
| ORM | SQLAlchemy 2.x async | Models + migrations via Alembic |
| Config | pydantic-settings + `.env` | Type-safe config, 12-factor |
| Logging | Python `logging` + `structlog` | JSON structured logs |
| Deployment | Docker container on a VPS | Single container, single process |

---

## 8. Deployment

### Options Considered

**Option A — Polling mode on a local machine**
Simplest possible deployment. Aiogram long-polls Telegram servers. No inbound ports needed. Cons: dependent on a machine being always-on; unstable for scheduled reminders.

**Option B — Webhook mode on a VPS (Recommended)**
Bot registers a webhook URL with Telegram. Telegram pushes updates via HTTPS POST. Aiogram's built-in aiohttp webhook server handles this. Lower latency than polling; works naturally on a small VPS.

**Option C — Serverless (e.g., AWS Lambda + API Gateway)**
Pros: zero cost when idle. Cons: cold starts delay reminders; APScheduler does not run reliably in stateless serverless functions; SQLite is incompatible with ephemeral function environments.

### Recommended Approach

Single Docker container on a small VPS (2 vCPU, 4GB RAM is comfortable — 2GB RAM is the practical minimum). The container runs:
- The Aiogram bot (webhook or polling, configurable)
- APScheduler (in the same event loop)
- ChromaDB (in-process persistent client)
- SQLite database file (mounted volume)

### Infrastructure Requirements

| Component | Specification |
|---|---|
| VPS | 2 vCPU, 4 GB RAM, 20 GB SSD |
| OS | Ubuntu 24.04 LTS |
| Container | Docker + Docker Compose |
| Volume | `/data` for SQLite DB, ChromaDB files, imports |
| HTTPS | Nginx reverse proxy with Let's Encrypt (for webhook mode) |
| Estimated cost | $15–25/month (DigitalOcean, Hetzner, or equivalent) |

### Persistent Volume Layout

```
/data/
  db.sqlite3          ← SQLite database (relational)
  chroma/             ← ChromaDB persistent storage
  imports/
    {user_id}/
      {batch_id}/     ← Raw imported files (kept for re-processing)
  logs/
    bot.log
```

### Environment Configuration (`.env`)

```
TELEGRAM_BOT_TOKEN=...
WEBHOOK_URL=https://yourdomain.com/webhook/{secret}
OPENAI_API_KEY=...            # Optional
OLLAMA_BASE_URL=...           # Optional, for local LLM
DATA_DIR=/data
EMBEDDING_MODEL=all-MiniLM-L6-v2
SCHEDULER_TIMEZONE=UTC
LOG_LEVEL=INFO
```

### Startup Sequence

1. `alembic upgrade head` (run migrations)
2. Start Aiogram bot (polling or webhook)
3. APScheduler starts, loads jobs from SQLite
4. ChromaDB client initializes from `/data/chroma`

### Rationale

A single container on a small VPS is the sweet spot for a personal single-user tool. It is always-on (required for cron reminders), cheap (~$20/month), easy to backup (just copy `/data`), and simple to operate. Serverless is not viable because APScheduler requires a persistent process.

---

## 9. Extensibility

### Adding New Heuristics

1. Create `bot/heuristics/my_new_heuristic.py` implementing the `heuristic(subject, context) -> float` callable.
2. Register it in `HeuristicRegistry.register("my_heuristic_name", my_new_heuristic)`.
3. Add default weight to the default `HeuristicProfile` config.
4. Add it to the `/settings` UI for user adjustment.

No core engine code changes required. The heuristic pipeline iterates over all registered and enabled heuristics.

### Adding New Platform Importers

1. Create `bot/importers/my_platform.py` implementing `PlatformImporter` Protocol.
2. Register in `ImporterRegistry`.
3. Add platform name to the `/import` wizard's platform selection inline keyboard.

No core import flow changes required.

### Adding API-Based Sync (future)

When a platform's OAuth API becomes viable:
1. Add an `OAuthConnector` class for the platform.
2. Store OAuth tokens in the `User` table (new encrypted column).
3. Add a background periodic job to APScheduler for sync.
4. The `PlatformImporter.parse()` method can accept either a file path or an API response — the parse contract remains the same.

### Adding New Reminder Strategies

Reminder triggers are APScheduler cron expressions. New trigger types (e.g., "post after big trending event") can be implemented as custom APScheduler triggers without changing the reminder data model.

### Multi-User Extension

The data model is user-scoped from day one (all tables carry `user_id`). Extending to multi-user requires:
- Replacing SQLite with PostgreSQL (one SQLAlchemy URL change).
- Moving from per-process ChromaDB to ChromaDB server mode or Qdrant server.
- Adding authentication (Telegram user ID is already the auth token).

### Heuristic Profile Sharing (future)

`HeuristicProfile` configs are stored as JSON. They could be exported/imported as text, allowing users to share their tuning with others, or for a curated "starter profile" to be seeded at onboarding.

### Rationale

All extension points are designed around the Open/Closed Principle: add new behavior by adding new files, not by modifying core logic. The registry pattern for heuristics and importers is the key mechanism. The user-scoped data model ensures multi-user is a scaling question, not a redesign question.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                      Docker Container                          │
│                                                                │
│  ┌──────────────────┐   ┌────────────────────────────────────┐ │
│  │   Aiogram Bot    │   │        APScheduler                 │ │
│  │                  │   │  (asyncio, same event loop)        │ │
│  │  Commands / FSM  │   │  Jobs: reminder_{id} per user      │ │
│  │  Inline KB       │   │  Store: SQLite apscheduler_jobs    │ │
│  │  Webhook server  │   └────────────┬───────────────────────┘ │
│  └────────┬─────────┘                │ fires job               │
│           │                          │                         │
│           └──────────┬───────────────┘                         │
│                      │ calls                                   │
│           ┌──────────▼───────────────────────────────────────┐ │
│           │            Application Services                   │ │
│           │                                                   │ │
│           │  SuggestionEngine (heuristics pipeline)          │ │
│           │  ImportService (platform adapters)               │ │
│           │  PredictionService (embeddings + clustering)     │ │
│           │  SchedulerService (APScheduler wrapper)          │ │
│           └──────┬──────────────────────────┬───────────────┘ │
│                  │                          │                  │
│     ┌────────────▼──────┐      ┌────────────▼──────────────┐  │
│     │  SQLite (aiosqlite)│      │  ChromaDB (persistent)   │  │
│     │  SQLAlchemy async  │      │  subject_embeddings      │  │
│     │                   │      │  strategy_embeddings      │  │
│     │  Users            │      └───────────────────────────┘  │
│     │  Subjects         │                                      │
│     │  Posts            │      ┌───────────────────────────┐  │
│     │  Reminders        │      │  /data/imports/           │  │
│     │  StrategyNotes    │      │  (raw export files)       │  │
│     │  HeuristicProfile │      └───────────────────────────┘  │
│     └───────────────────┘                                      │
└────────────────────────────────────────────────────────────────┘
                              │ HTTPS
                    ┌─────────▼──────────┐
                    │   Telegram Servers │
                    └────────────────────┘
```

---

## Open Questions and Risks

### Resolve Before Implementation

1. **Single-user vs multi-user scope at launch.** The design supports one user per deployment instance. If multi-user is needed at launch, PostgreSQL and ChromaDB server mode must be adopted from the start — this is not a trivial post-launch change. Decision needed before database schema is finalized.

2. **LLM provider default.** Should the bot work without any LLM API key (prediction via clustering only), or require an API key (better suggestion quality from day one)? Clustering-only mode is technically viable but produces lower-quality subject labels. Recommended: make LLM optional, gracefully degrade to cluster-centroid text as label.

3. **Cooldown policy.** The default recency cooldown (14 days before re-suggesting a subject) is assumed. The correct value depends on the user's posting strategy and platform. Should this be per-platform or global? Recommend: global default at first, per-platform in a later iteration.

4. **Telegram file size limit for imports.** Telegram bots can receive files up to 20 MB via the Bot API. Large Instagram or TikTok data exports can exceed this. The import flow needs a fallback for oversized files (e.g., instruct user to compress, or provide an alternative upload mechanism). Verify this limit before implementing the import wizard.

### Deferred to Planning

5. **[Affects importer] Needs research:** Exact JSON schema of Instagram, TikTok, and Threads data export packages varies by user account type and export date. The importer's field-mapping logic must be validated against real export samples before implementation.

6. **[Affects prediction] Technical:** DBSCAN epsilon and min_samples hyperparameters for the clustering step need empirical tuning. A reasonable starting default (epsilon=0.3, min_samples=2) should be validated against a small sample of real posting history before shipping.

7. **[Affects scheduler] Resolved:** APScheduler 3.x asyncio integration with Aiogram 3's event loop — resolved by starting `AsyncIOScheduler` inside Aiogram's `on_startup` hook. This shares the already-running event loop. Note: APScheduler 4.x has an entirely different API (`AsyncScheduler` + `SQLAlchemyDataStore`); the project uses 3.x with `SQLAlchemyJobStore` (synchronous, `sqlite:///` URL).

8. **[Affects deployment] Needs research:** SQLite WAL mode behavior under concurrent reads from the bot handler and APScheduler writer. At single-user scale this is unlikely to be a problem, but WAL mode should be explicitly enabled in the SQLAlchemy engine config.

9. **[Affects strategy weighting] Technical:** The strategy alignment heuristic relies on cosine similarity between subject and strategy note embeddings. If a user has many long strategy notes, averaging embeddings may lose signal. Evaluate max-pooling or top-K similarity as alternatives during planning.

---

## Next Steps

All critical product decisions are resolved in this document. The recommended next step is implementation planning.

`→ /ce:plan` using this document as the foundation.
