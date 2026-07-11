"""
bot/config.py

Загрузка настроек из .env + константы бота.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Константы (в будущем — персональные настройки пользователя)
MORNING_HOUR = 8
MORNING_MINUTE = 0
MIDDAY_HOUR = 14
MIDDAY_MINUTE = 0
HISTORY_LIMIT = 30
MAX_ACTIONS = 5
TELEGRAM_MESSAGE_LIMIT = 4096
MAX_VOICE_SECONDS = 300


@dataclass(frozen=True)
class Config:
    bot_token: str
    fernet_master_key: str
    admin_telegram_id: int | None
    ollama_host: str
    whisper_model: str
    whisper_device: str

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env")

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        fernet_master_key = os.getenv("FERNET_MASTER_KEY", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN не задан в .env")
        if not fernet_master_key:
            raise RuntimeError("FERNET_MASTER_KEY не задан в .env")

        admin_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
        admin_telegram_id = int(admin_raw) if admin_raw else None

        ollama_host = os.getenv("OLLAMA_HOST", "").strip() or "http://localhost:11434"
        whisper_model = os.getenv("WHISPER_MODEL", "").strip() or "small"
        whisper_device = os.getenv("WHISPER_DEVICE", "").strip() or "cpu"

        return cls(
            bot_token=bot_token,
            fernet_master_key=fernet_master_key,
            admin_telegram_id=admin_telegram_id,
            ollama_host=ollama_host,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
        )
