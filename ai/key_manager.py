"""
ai/key_manager.py

Owns all DB + Fernet concerns for per-user AI provider API keys, so the
concrete client classes (ClaudeClient, OllamaClient, ...) never touch the
database or crypto.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from db.init_db import DB_PATH


class KeyManagerError(Exception):
    """Raised when a usable API key cannot be resolved for a user/provider."""


class KeyManager:
    """Looks up a user's encrypted API key for a provider in ai_provider_keys
    and decrypts it with the Fernet master key (loaded from .env by the
    caller)."""

    def __init__(self, master_key: str, db_path: Path = DB_PATH) -> None:
        self._fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        self._db_path = db_path

    def get_active_key(self, user_id: int, provider: str) -> str:
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT encrypted_key FROM ai_provider_keys "
                "WHERE user_id = ? AND provider = ? AND is_active = 1 LIMIT 1",
                (user_id, provider),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            raise KeyManagerError(f"No active {provider} key found for user {user_id}")

        try:
            return self._fernet.decrypt(row[0].encode()).decode()
        except InvalidToken as exc:
            raise KeyManagerError(
                f"Stored key for user {user_id}/{provider} could not be decrypted"
            ) from exc

    def store_key(
        self,
        user_id: int,
        provider: str,
        plaintext_key: str,
        label: str | None = None,
        make_active: bool = True,
    ) -> None:
        encrypted = self._fernet.encrypt(plaintext_key.encode()).decode()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            if make_active:
                conn.execute(
                    "UPDATE ai_provider_keys SET is_active = 0 WHERE user_id = ? AND provider = ?",
                    (user_id, provider),
                )
            conn.execute(
                "INSERT INTO ai_provider_keys (user_id, provider, label, encrypted_key, is_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, provider, label, encrypted, int(make_active)),
            )
            conn.commit()
        finally:
            conn.close()
