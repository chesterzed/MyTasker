"""
bot/services/queries.py

Валидация read-запросов, которые модель может вернуть в поле "queries"
(в отличие от write-«actions», выполняются сразу и без подтверждения).
Белый список имён + нормализация параметров — по образцу actions.validate_actions.
"""
from __future__ import annotations

import sqlite3

from bot.utils import is_iso_date, today_local

MAX_QUERIES = 5

VALID_QUERIES = {"list_tasks", "list_all_tasks", "list_goals"}


def validate_queries(queries: list[dict], db_user: sqlite3.Row) -> list[dict]:
    """Нормализованные read-запросы; неизвестные/битые молча отбрасываются."""
    out: list[dict] = []
    for q in queries[:MAX_QUERIES]:
        name = q.get("name")
        if name not in VALID_QUERIES:
            continue
        if name == "list_tasks":
            date = q.get("date")
            if not is_iso_date(date):
                date = today_local(db_user)  # дефолт — сегодня
            out.append({"name": "list_tasks", "date": date})
        elif name == "list_all_tasks":
            out.append({"name": "list_all_tasks"})
        elif name == "list_goals":
            out.append({"name": "list_goals"})
    return out
