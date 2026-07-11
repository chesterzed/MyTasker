"""
bot/services/actions.py

Валидация предложенных моделью действий и их применение к БД
(путь «Подтвердить»).
"""
from __future__ import annotations

import html
import re

from bot import texts
from bot.config import MAX_ACTIONS
from bot.services import repository as repo

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TITLE_MAX = 200

VALID_TYPES = {"add_goal", "add_task", "complete_task", "reschedule"}


def _clean_str(value, max_len: int = _TITLE_MAX) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_len] if value else None


def _valid_date(value) -> bool:
    return isinstance(value, str) and bool(_DATE_RE.match(value))


def validate_action(action: dict, user_id: int) -> dict | None:
    """Нормализованное действие или None (невалидные молча отбрасываются)."""
    type_ = action.get("type")
    if type_ not in VALID_TYPES:
        return None

    if type_ == "add_goal":
        title = _clean_str(action.get("title"))
        if not title:
            return None
        priority = action.get("priority", 0)
        if not isinstance(priority, int) or not (0 <= priority <= 10):
            priority = 0
        target_date = action.get("target_date")
        if target_date is not None and not _valid_date(target_date):
            target_date = None
        return {
            "type": "add_goal",
            "title": title,
            "description": _clean_str(action.get("description"), 1000),
            "priority": priority,
            "target_date": target_date,
        }

    if type_ == "add_task":
        title = _clean_str(action.get("title"))
        if not title or not _valid_date(action.get("date")):
            return None
        goal_id = action.get("goal_id")
        if goal_id is not None and (
            not isinstance(goal_id, int) or not repo.goal_exists(user_id, goal_id)
        ):
            goal_id = None
        return {
            "type": "add_task",
            "title": title,
            "description": _clean_str(action.get("description"), 1000),
            "date": action["date"],
            "goal_id": goal_id,
        }

    # complete_task / reschedule — task_id обязан существовать и принадлежать пользователю
    task_id = action.get("task_id")
    if not isinstance(task_id, int):
        return None
    task = repo.get_task(task_id)
    if task is None or task["user_id"] != user_id:
        return None

    if type_ == "complete_task":
        return {"type": "complete_task", "task_id": task_id}

    if not _valid_date(action.get("new_date")):
        return None
    return {"type": "reschedule", "task_id": task_id, "new_date": action["new_date"]}


def validate_actions(actions: list[dict], user_id: int) -> list[dict]:
    valid = []
    for action in actions[:MAX_ACTIONS]:
        normalized = validate_action(action, user_id)
        if normalized is not None:
            valid.append(normalized)
    return valid


def render_action_line(action: dict) -> str:
    """Человекочитаемая строка действия для сообщения-предложения (HTML)."""
    type_ = action["type"]
    if type_ == "add_goal":
        return texts.ACTION_ADD_GOAL.format(title=html.escape(action["title"]))
    if type_ == "add_task":
        return texts.ACTION_ADD_TASK.format(
            title=html.escape(action["title"]), date=action["date"]
        )
    task = repo.get_task(action["task_id"])
    title = html.escape(task["title"]) if task else f"задача #{action['task_id']}"
    if type_ == "complete_task":
        return texts.ACTION_COMPLETE_TASK.format(title=title)
    return texts.ACTION_RESCHEDULE.format(title=title, date=action["new_date"])


def apply_all(user_id: int, actions: list[dict]) -> list[str]:
    """Применяет подтверждённые действия; возвращает строки результата (HTML)."""
    results = []
    for action in actions:
        type_ = action["type"]
        if type_ == "add_goal":
            repo.add_goal(
                user_id,
                title=action["title"],
                description=action["description"],
                priority=action["priority"],
                target_date=action["target_date"],
            )
            results.append(texts.RESULT_GOAL_ADDED.format(title=html.escape(action["title"])))
        elif type_ == "add_task":
            repo.add_task(
                user_id,
                title=action["title"],
                date=action["date"],
                description=action["description"],
                goal_id=action["goal_id"],
                source="ai",
            )
            results.append(
                texts.RESULT_TASK_ADDED.format(
                    title=html.escape(action["title"]), date=action["date"]
                )
            )
        elif type_ == "complete_task":
            task = repo.get_task(action["task_id"])
            repo.mark_task_done(action["task_id"])
            title = html.escape(task["title"]) if task else f"#{action['task_id']}"
            results.append(texts.RESULT_TASK_COMPLETED.format(title=title))
        elif type_ == "reschedule":
            task = repo.get_task(action["task_id"])
            repo.set_task_date(action["task_id"], action["new_date"])
            title = html.escape(task["title"]) if task else f"#{action['task_id']}"
            results.append(
                texts.RESULT_TASK_RESCHEDULED.format(title=title, date=action["new_date"])
            )
    return results
