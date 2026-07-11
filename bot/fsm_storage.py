"""
bot/fsm_storage.py

FSM-хранилище aiogram поверх колонок users.fsm_state / users.fsm_context —
состояние диалога переживает перезапуск бота.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from db.init_db import DB_PATH


class SQLiteFSMStorage(BaseStorage):
    """Ключ — StorageKey.user_id (= telegram_id; бот работает в приватных чатах,
    поэтому chat_id совпадает и не используется)."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _ensure_user(self, conn: sqlite3.Connection, telegram_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (telegram_id,)
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        with self._connect() as conn:
            self._ensure_user(conn, key.user_id)
            conn.execute(
                "UPDATE users SET fsm_state = ? WHERE telegram_id = ?",
                (value, key.user_id),
            )

    async def get_state(self, key: StorageKey) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fsm_state FROM users WHERE telegram_id = ?", (key.user_id,)
            ).fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        value = json.dumps(data, ensure_ascii=False) if data else None
        with self._connect() as conn:
            self._ensure_user(conn, key.user_id)
            conn.execute(
                "UPDATE users SET fsm_context = ? WHERE telegram_id = ?",
                (value, key.user_id),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fsm_context FROM users WHERE telegram_id = ?", (key.user_id,)
            ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return {}

    async def close(self) -> None:
        pass
