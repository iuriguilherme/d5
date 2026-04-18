# WDWGN

**Where Do We Go Now** — Telegram bot for organizing social media content subjects, tracking posting history, and receiving AI-assisted suggestions.

Single-user, self-hosted, privacy-first. No cloud accounts required beyond a Telegram bot token. LLM integration is optional.

## Features

- `/idea` — Add content subject ideas to your pool
- `/pool` — Browse and manage your subject pool
- `/suggest` — Get an AI-scored suggestion of what to post next
- `/posted` — Record what you posted and on which platform
- `/schedule` — Set cron-based reminders per platform
- `/import` — Import posting history from Instagram, TikTok, Threads, or CSV
- `/strategy` — Store content strategy notes (embedded and used in scoring)
- `/settings` — Tune heuristic weights and cooldown period

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | Aiogram 3.x (asyncio, FSM, webhooks/polling) |
| Database | SQLite via aiosqlite + SQLAlchemy 2.x async |
| Vector DB | ChromaDB (local, SQLite-backed) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local, no API) |
| Scheduler | APScheduler 3.x AsyncIOScheduler |
| LLM (optional) | OpenAI GPT-4o-mini or Ollama |
| Deployment | Docker + optional Nginx (webhook mode) |

## Quick Start

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN in .env
docker compose up
```

For webhook mode, also set `WEBHOOK_URL`, `WEBHOOK_SECRET`, and `DOMAIN` in `.env`, then:

```bash
docker compose --profile webhook up
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `ALLOWED_USER_IDS` | No | (all) | Comma-separated Telegram user IDs |
| `WEBHOOK_URL` | No | — | Full HTTPS URL; enables webhook mode |
| `WEBHOOK_SECRET` | No | — | Webhook secret token |
| `DOMAIN` | No | — | VPS hostname for Nginx |
| `OPENAI_API_KEY` | No | — | Enables LLM-enriched subject clustering |
| `DATA_DIR` | No | `/data` | Persistent data directory |
| `SCHEDULER_TIMEZONE` | No | `UTC` | Timezone for cron reminders |
| `COOLDOWN_DAYS` | No | `14` | Default cooldown between re-suggesting a subject |

## License

GPLv3 - see [LICENSE](./LICENSE)

    Copyright (C) 2026  Iuri Guilherme

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
