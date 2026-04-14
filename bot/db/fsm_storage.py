"""SQLite-backed Aiogram FSM storage.

Implements aiogram.fsm.storage.base.BaseStorage over aiosqlite so that
FSM state survives bot restarts. State is stored in the `fsm_state` table
created by Alembic migration 0001.
"""
import json
from typing import Any

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey


class SqliteStorage(BaseStorage):
    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Path to the SQLite database file (not the SQLAlchemy URL).
                     Example: "/data/wdwgn.db"
        """
        self._db_path = db_path

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_str = state.state if isinstance(state, State) else state
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO fsm_state (user_id, chat_id, state)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET state = excluded.state
                """,
                (key.user_id, key.chat_id, state_str),
            )
            await db.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT state FROM fsm_state WHERE user_id = ? AND chat_id = ?",
                (key.user_id, key.chat_id),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO fsm_state (user_id, chat_id, data)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET data = excluded.data
                """,
                (key.user_id, key.chat_id, json.dumps(data)),
            )
            await db.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT data FROM fsm_state WHERE user_id = ? AND chat_id = ?",
                (key.user_id, key.chat_id),
            ) as cursor:
                row = await cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return {}

    async def close(self) -> None:
        pass  # aiosqlite connections are opened per-operation; nothing to close
