"""
bot/services/planning.py

Немедленное планирование задачи из только что добавленной цели: если день ещё
не закончился (до вечернего порога пользователя) и есть свободный бюджет времени,
просим нейросеть разбить цель в одну конкретную задачу на сегодня.

Любой сбой (нет доступа/ключа, ошибка сети/ИИ, непарсибельный ответ) деградирует
в «ничего не добавили» — цель уже сохранена, ронять диалог нельзя.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from ai.base import AIClientError, ChatMessage
from ai.key_manager import KeyManager
from bot.config import DAILY_CAPACITY_MINUTES, Config
from bot.services import actions as actions_service
from bot.services import ai_orchestrator as orchestrator
from bot.services import prompts
from bot.services import repository as repo
from bot.utils import today_local, user_tz

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("pending", "moved")


def has_time_left_today(db_user: sqlite3.Row) -> bool:
    """Ещё не поздно планировать: местный час < порога пользователя."""
    return datetime.now(user_tz(db_user)).hour < db_user["planning_cutoff_hour"]


def remaining_budget_minutes(user_id: int, date: str) -> int:
    """Сколько минут дневного бюджета ещё свободно (уже занятые задачи вычитаем)."""
    booked = 0
    for t in repo.list_tasks_for_date(user_id, date):
        if t["status"] in _ACTIVE_STATUSES and t["estimate_minutes"]:
            booked += t["estimate_minutes"]
    return DAILY_CAPACITY_MINUTES - booked


async def generate_plan_for_goal(
    db_user: sqlite3.Row, goal_id: int, config: Config, key_manager: KeyManager
) -> int:
    """Составить нейросетью подробный план цели (goal_steps, полная замена).
    Возвращает число созданных шагов; 0 = не вышло. Исключений наружу не бросает."""
    try:
        return await _generate_plan(db_user, goal_id, config, key_manager)
    except Exception:
        logger.exception("generate_plan_for_goal failed for user %s", db_user["id"])
        return 0


async def _generate_plan(
    db_user: sqlite3.Row, goal_id: int, config: Config, key_manager: KeyManager
) -> int:
    user_id = db_user["id"]
    goal = repo.get_goal(user_id, goal_id)
    if goal is None:
        return 0

    try:
        client = orchestrator.build_client(db_user, config, key_manager)
    except orchestrator.ClientConfigError:
        logger.info("planning: user %s has no AI configured, skipping plan", user_id)
        return 0

    system_prompt = orchestrator.build_plan_system_prompt(db_user, goal)
    try:
        raw = await client.send_message(
            [ChatMessage(role="user", content=prompts.PLAN_TRIGGER)],
            system_prompt=system_prompt,
            max_tokens=2048,  # подробный план из 20 шагов не влезает в дефолтные 1024
        )
    except AIClientError:
        logger.exception("planning: AI plan call failed for user %s", user_id)
        return 0

    proposed = orchestrator.parse_plan_response(raw)
    steps = actions_service._clean_plan_steps(proposed)
    if not steps:
        logger.warning("planning: unparseable plan response for user %s", user_id)
        return 0
    return repo.replace_goal_steps(user_id, goal_id, steps)


async def generate_today_task_for_goal(
    db_user: sqlite3.Row, goal_id: int, config: Config, key_manager: KeyManager
) -> list[sqlite3.Row]:
    """Возвращает добавленные задачи (0 или 1). Никогда не бросает исключений наружу."""
    try:
        return await _generate(db_user, goal_id, config, key_manager)
    except Exception:
        logger.exception("generate_today_task_for_goal failed for user %s", db_user["id"])
        return []


async def _generate(
    db_user: sqlite3.Row, goal_id: int, config: Config, key_manager: KeyManager
) -> list[sqlite3.Row]:
    user_id = db_user["id"]
    goal = repo.get_goal(user_id, goal_id)
    if goal is None:
        return []

    today = today_local(db_user)
    remaining = remaining_budget_minutes(user_id, today)
    if remaining <= 0:
        return []

    try:
        client = orchestrator.build_client(db_user, config, key_manager)
    except orchestrator.ClientConfigError:
        logger.info("planning: user %s has no AI configured, skipping", user_id)
        return []

    system_prompt = orchestrator.build_goal_task_system_prompt(db_user, goal, remaining)
    try:
        raw = await client.send_message(
            [ChatMessage(role="user", content=prompts.GOAL_TASK_TRIGGER)],
            system_prompt=system_prompt,
        )
    except AIClientError:
        logger.exception("planning: AI call failed for user %s", user_id)
        return []

    proposed = orchestrator.parse_morning_response(raw)
    added: list[sqlite3.Row] = []
    for t in proposed[:1]:
        title = t.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        description = t.get("description")
        if not isinstance(description, str):
            description = None
        estimate = t.get("estimate_minutes")
        if not isinstance(estimate, int) or isinstance(estimate, bool) or estimate <= 0:
            estimate = None
        elif estimate > remaining:
            estimate = remaining
        task_id = repo.add_task(
            user_id,
            title=title.strip()[:200],
            date=today,
            description=description,
            goal_id=goal_id,
            source="ai",
            estimate_minutes=estimate,
        )
        task = repo.get_task(task_id)
        if task is not None:
            added.append(task)
    return added
