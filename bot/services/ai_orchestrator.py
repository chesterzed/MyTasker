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
# Старый служебный маркер в логах ассистента — вырезаем из истории, чтобы модель
# его не видела и не парротила (см. переход на assistant_turn_json).
_ACTION_MARKER_RE = re.compile(r"\n?\[предложены действия:[^\]]*\]")


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

def _step_line(step: sqlite3.Row) -> str:
    mark = "✅" if step["status"] == "done" else "⬜"
    progress = ""
    if step["progress_total"]:
        progress = f" ({step['progress_current']}/{step['progress_total']})"
    return f"[step_id={step['id']}] {mark} {step['title']}{progress}"


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
        # план цели — модель и отмечает шаги (update_step), и опирается на них утром
        steps = repo.list_goal_steps(g["id"])
        if steps:
            lines.append("  план:")
            lines.extend(f"  {_step_line(s)}" for s in steps)
        else:
            lines.append("  (плана пока нет)")
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


def _carried_note(task: sqlite3.Row) -> str:
    """« (перенесена с YYYY-MM-DD)» для задачи, чья активная дата ушла вперёд."""
    planned = task["planned_date"] if "planned_date" in task.keys() else None
    if planned and planned != task["date"]:
        return f" (перенесена с {planned})"
    return ""


def _tasks_block(user_id: int, date: str) -> str:
    tasks = repo.list_tasks_for_date(user_id, date)
    if not tasks:
        return prompts.TASKS_EMPTY
    return "\n".join(
        f"[task_id={t['id']}] {t['title']} — {t['status']}{_carried_note(t)}" for t in tasks
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


def build_plan_system_prompt(db_user: sqlite3.Row, goal: sqlite3.Row) -> str:
    today, weekday = _today_weekday(db_user)
    return prompts.SYSTEM_PLAN.format(
        today=today,
        weekday=weekday,
        goal_block=_single_goal_block(goal),
    )


def build_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
    """История из messages_log под требования Anthropic: роли чередуются,
    первое сообщение — user (подряд идущие одинаковые роли сливаются)."""
    merged: list[ChatMessage] = []
    for row in repo.recent_messages(user_id, limit):
        text = row["text"]
        if row["role"] == "assistant":
            text = _ACTION_MARKER_RE.sub("", text)
        if merged and merged[-1].role == row["role"]:
            merged[-1] = ChatMessage(
                role=row["role"], content=merged[-1].content + "\n\n" + text
            )
        else:
            merged.append(ChatMessage(role=row["role"], content=text))
    while merged and merged[0].role == "assistant":
        merged.pop(0)
    return merged


# ── парсинг ответов модели ───────────────────────────────────────

@dataclass
class ParsedResponse:
    reply: str
    actions: list[dict] = field(default_factory=list)
    queries: list[dict] = field(default_factory=list)


def assistant_turn_json(reply: str, actions: list[dict]) -> str:
    """Канонический вид ассистентского хода для messages_log/истории.

    В истории модель должна видеть свои прошлые ходы в ТОМ ЖЕ формате, что
    обязана выдавать (строгий JSON-контракт) — иначе она имитирует прозу из
    истории и перестаёт эмитить actions (тогда кнопки не показываются)."""
    return json.dumps({"reply": reply, "actions": actions}, ensure_ascii=False)


def _extract_json(raw: str) -> dict | None:
    """Достаёт первый валидный JSON-объект из ответа модели, даже если он
    окружён прозой. Сканируем от каждой «{» через raw_decode (парсит один
    JSON-документ и игнорирует хвост); скобки-«обманки» в прозе пропускаем."""
    text = _FENCE_RE.sub("", raw.strip()).strip()
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx = text.find("{", idx + 1)
            continue
        if isinstance(obj, dict):
            return obj
        idx = text.find("{", idx + 1)
    return None


def parse_ai_response(raw: str) -> ParsedResponse:
    """Никогда не роняет диалог. Сырой текст уходит в reply только если это не
    JSON ЛИБО JSON пуст и без действий (иначе actions сохраняем, даже при пустом
    reply — иначе валидные действия терялись бы, а в чат летел сырой JSON)."""
    data = _extract_json(raw)
    if data is None:
        return ParsedResponse(reply=raw.strip())
    actions_raw = data.get("actions")
    actions = (
        [a for a in actions_raw if isinstance(a, dict)]
        if isinstance(actions_raw, list)
        else []
    )
    queries_raw = data.get("queries")
    queries = (
        [q for q in queries_raw if isinstance(q, dict)]
        if isinstance(queries_raw, list)
        else []
    )
    reply = data.get("reply")
    reply = reply.strip() if isinstance(reply, str) else ""
    if not reply and not actions and not queries:
        return ParsedResponse(reply=raw.strip())
    return ParsedResponse(reply=reply, actions=actions, queries=queries)


def parse_morning_response(raw: str) -> list[dict]:
    data = _extract_json(raw)
    if data is None:
        return []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, dict)]


def parse_plan_response(raw: str) -> list[dict]:
    data = _extract_json(raw)
    if data is None:
        return []
    steps = data.get("steps")
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]
