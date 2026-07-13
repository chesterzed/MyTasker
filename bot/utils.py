"""
bot/utils.py

Мелкие общие хелперы.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.config import TELEGRAM_MESSAGE_LIMIT


def user_tz(db_user: sqlite3.Row) -> ZoneInfo:
    try:
        return ZoneInfo(db_user["timezone"] or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def today_local(db_user: sqlite3.Row) -> str:
    """Сегодняшняя дата (YYYY-MM-DD) в часовом поясе пользователя."""
    return datetime.now(user_tz(db_user)).date().isoformat()


def has_access(db_user: sqlite3.Row) -> bool:
    """AI-пути доступны админу всегда; обычному пользователю — при живой подписке."""
    if db_user["role"] == "admin":
        return True
    until = db_user["subscription_until"]
    if not until:
        return False
    return until >= datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def step_progress_suffix(step: sqlite3.Row) -> str:
    """« (2/3)» для счётного шага плана, иначе пустая строка."""
    if step["progress_total"]:
        return f" ({step['progress_current']}/{step['progress_total']})"
    return ""


def truncate(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
