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

# Времена напоминаний по умолчанию (посев новым пользователям); дальше
# редактируются персонально через /notifications (таблица reminders).
DEFAULT_REMINDER_TIMES = ("08:00", "14:00")
# С какого часа местного времени напоминание считается «вечерним»
# (тон «скоро дедлайн» / «подведём итог»).
EVENING_HOUR = 18
HISTORY_LIMIT = 30
MAX_ACTIONS = 5
TELEGRAM_MESSAGE_LIMIT = 4096
MAX_VOICE_SECONDS = 300

# Планирование дня: сколько всего минут задач в день считаем посильным (~8 часов)
# и до какого часа местного времени по умолчанию имеет смысл добавлять задачи
# на сегодня (порог редактируется на пользователя, колонка users.planning_cutoff_hour).
DAILY_CAPACITY_MINUTES = 480
DEFAULT_PLANNING_CUTOFF_HOUR = 21

# Сколько моделей на странице экрана /settings → Модель.
MODELS_PER_PAGE = 5
_VALID_PROVIDERS = ("claude", "ollama")
# Дефолтный список моделей, если AI_MODELS не задан в .env (используемые сейчас).
_DEFAULT_AI_MODELS = "claude:claude-opus-4-8,ollama:qwen2.5:14b"


@dataclass(frozen=True)
class AiModel:
    provider: str   # 'claude' | 'ollama'
    model: str      # id модели, он же подпись кнопки


def _parse_ai_models(raw: str) -> tuple[AiModel, ...]:
    """Пары 'провайдер:модель' через запятую. Split по ПЕРВОМУ ':' — модели
    ollama сами содержат ':' (qwen2.5:14b). Битые записи молча отбрасываются."""
    models: list[AiModel] = []
    for item in raw.split(","):
        item = item.strip()
        if ":" not in item:
            continue
        provider, model = item.split(":", 1)
        provider, model = provider.strip(), model.strip()
        if provider in _VALID_PROVIDERS and model:
            models.append(AiModel(provider=provider, model=model))
    return tuple(models)


@dataclass(frozen=True)
class Config:
    bot_token: str
    fernet_master_key: str
    admin_telegram_id: int | None
    ollama_host: str
    whisper_model: str
    whisper_device: str
    telegram_proxy: str | None
    ai_models: tuple[AiModel, ...]

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
        # Прокси до api.telegram.org (нужен там, где Telegram недоступен напрямую).
        # Примеры: socks5://127.0.0.1:2080  или  http://127.0.0.1:8080
        telegram_proxy = os.getenv("TELEGRAM_PROXY", "").strip() or None
        ai_models = _parse_ai_models(
            os.getenv("AI_MODELS", "").strip() or _DEFAULT_AI_MODELS
        )
        if not ai_models:  # весь список оказался битым — не оставлять экран пустым
            ai_models = _parse_ai_models(_DEFAULT_AI_MODELS)

        return cls(
            bot_token=bot_token,
            fernet_master_key=fernet_master_key,
            admin_telegram_id=admin_telegram_id,
            ollama_host=ollama_host,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            telegram_proxy=telegram_proxy,
            ai_models=ai_models,
        )
