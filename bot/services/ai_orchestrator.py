"""
bot/services/ai_orchestrator.py

Слой между ботом и AI-клиентами: фабрика клиента по users.ai_provider,
сборка контекста и истории, робастный парсинг JSON-ответов модели.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from ai.base import BaseAIClient, ChatMessage
from ai.claude_client import ClaudeClient
from ai.key_manager import KeyManager, KeyManagerError
from ai.ollama_client import OllamaClient
from bot.config import DAILY_CAPACITY_MINUTES, HISTORY_LIMIT, MAX_ACTIONS, Config
from bot.services import prompts
from bot.services import repository as repo
from bot.utils import today_local, user_tz

_WEEKDAYS_RU = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ClientConfigError(Exception):
    """Провайдер пользователя не настроен (нет ключа / модели)."""


def build_client(db_user: sqlite3.Row, config: Config, key_manager: KeyManager) -> BaseAIClient:
    provider = db_user["ai_provider"]
    if provider == "ollama":
        model = db_user["ollama_model"]
        if not model:
            raise ClientConfigError("ollama model is not set")
        return OllamaClient(default_model=model, host=config.ollama_host)
    try:
        api_key = key_manager.get_active_key(db_user["id"], "claude")
    except KeyManagerError as exc:
        raise ClientConfigError(str(exc)) from exc
    return ClaudeClient(api_key=api_key)


# ── сборка контекста ─────────────────────────────────────────────

def _goals_block(user_id: int) -> str:
    goals = repo.list_active_goals(user_id)
    if not goals:
        return prompts.GOALS_EMPTY
    lines = []
    for g in goals:
        line = f"[goal_id={g['id']}] {g['title']}"
        extras = []
        if g["priority"]:
            extras.append(f"приоритет {g['priority']}")
        if g["target_date"]:
            extras.append(f"срок {g['target_date']}")
        if g["description"]:
            extras.append(g["description"])
        if extras:
            line += " — " + ", ".join(extras)
        lines.append(line)
    return "\n".join(lines)


def _single_goal_block(goal: sqlite3.Row) -> str:
    line = f"[goal_id={goal['id']}] {goal['title']}"
    extras = []
    if goal["priority"]:
        extras.append(f"приоритет {goal['priority']}")
    if goal["target_date"]:
        extras.append(f"срок {goal['target_date']}")
    if goal["description"]:
        extras.append(goal["description"])
    if extras:
        line += " — " + ", ".join(extras)
    return line


def _today_tasks_estimates_block(user_id: int, date: str) -> str:
    tasks = repo.list_tasks_for_date(user_id, date)
    if not tasks:
        return prompts.TASKS_EMPTY
    lines = []
    for t in tasks:
        est = t["estimate_minutes"]
        suffix = f" — ~{est} мин" if est else ""
        lines.append(f"«{t['title']}» — {t['status']}{suffix}")
    return "\n".join(lines)


def _tasks_block(user_id: int, date: str) -> str:
    tasks = repo.list_tasks_for_date(user_id, date)
    if not tasks:
        return prompts.TASKS_EMPTY
    return "\n".join(
        f"[task_id={t['id']}] {t['title']} — {t['status']}" for t in tasks
    )


def _history_block(user_id: int) -> str:
    rows = repo.recent_task_history(user_id, days=7)
    if not rows:
        return prompts.HISTORY_EMPTY
    status_ru = {"done": "выполнена", "pending": "не выполнена", "skipped": "пропущена", "moved": "перенесена"}
    return "\n".join(
        f"{t['date']} — «{t['title']}» — {status_ru.get(t['status'], t['status'])}"
        for t in rows
    )


def _today_weekday(db_user: sqlite3.Row) -> tuple[str, str]:
    now = datetime.now(user_tz(db_user))
    return now.date().isoformat(), _WEEKDAYS_RU[now.weekday()]


def build_chat_system_prompt(db_user: sqlite3.Row, checkin_active: bool = False) -> str:
    today, weekday = _today_weekday(db_user)
    return prompts.SYSTEM_CHAT.format(
        today=today,
        weekday=weekday,
        tz=db_user["timezone"] or "UTC",
        goals_block=_goals_block(db_user["id"]),
        tasks_block=_tasks_block(db_user["id"], today_local(db_user)),
        checkin_block=prompts.CHECKIN_BLOCK if checkin_active else "",
        max_actions=MAX_ACTIONS,
    )


def build_morning_system_prompt(db_user: sqlite3.Row) -> str:
    today, weekday = _today_weekday(db_user)
    return prompts.SYSTEM_MORNING.format(
        today=today,
        weekday=weekday,
        goals_block=_goals_block(db_user["id"]),
        history_block=_history_block(db_user["id"]),
    )


def build_goal_task_system_prompt(
    db_user: sqlite3.Row, goal: sqlite3.Row, remaining_minutes: int
) -> str:
    today, weekday = _today_weekday(db_user)
    return prompts.SYSTEM_GOAL_TASK.format(
        today=today,
        weekday=weekday,
        goal_block=_single_goal_block(goal),
        today_tasks_block=_today_tasks_estimates_block(db_user["id"], today),
        remaining_minutes=remaining_minutes,
        capacity_minutes=DAILY_CAPACITY_MINUTES,
        goal_id=goal["id"],
    )


def build_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
    """История из messages_log под требования Anthropic: роли чередуются,
    первое сообщение — user (подряд идущие одинаковые роли сливаются)."""
    merged: list[ChatMessage] = []
    for row in repo.recent_messages(user_id, limit):
        if merged and merged[-1].role == row["role"]:
            merged[-1] = ChatMessage(
                role=row["role"], content=merged[-1].content + "\n\n" + row["text"]
            )
        else:
            merged.append(ChatMessage(role=row["role"], content=row["text"]))
    while merged and merged[0].role == "assistant":
        merged.pop(0)
    return merged


# ── парсинг ответов модели ───────────────────────────────────────

@dataclass
class ParsedResponse:
    reply: str
    actions: list[dict] = field(default_factory=list)


def _extract_json(raw: str) -> dict | None:
    text = _FENCE_RE.sub("", raw.strip()).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_ai_response(raw: str) -> ParsedResponse:
    """Никогда не роняет диалог: при любой неудаче весь текст — обычный reply."""
    data = _extract_json(raw)
    if data is None:
        return ParsedResponse(reply=raw.strip())
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return ParsedResponse(reply=raw.strip())
    actions = data.get("actions")
    if not isinstance(actions, list):
        actions = []
    return ParsedResponse(reply=reply.strip(), actions=[a for a in actions if isinstance(a, dict)])


def parse_morning_response(raw: str) -> list[dict]:
    data = _extract_json(raw)
    if data is None:
        return []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, dict)]
