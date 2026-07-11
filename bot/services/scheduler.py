"""
bot/services/scheduler.py

APScheduler: per-user cron-джобы «утро» (генерация плана) и «день» (чек-ин)
в часовом поясе пользователя. Ссылки на bot/config/key_manager задаются
из main.py через setup().
"""
from __future__ import annotations

import logging
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ai.base import AIClientError, ChatMessage
from ai.key_manager import KeyManager
from bot import texts
from bot.config import MIDDAY_HOUR, MIDDAY_MINUTE, MORNING_HOUR, MORNING_MINUTE, Config
from bot.services import ai_orchestrator as orchestrator
from bot.services import prompts
from bot.services import repository as repo
from bot.utils import has_access, today_local, truncate

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_scheduler: AsyncIOScheduler | None = None
_config: Config | None = None
_key_manager: KeyManager | None = None


def setup(bot: Bot, scheduler: AsyncIOScheduler, config: Config, key_manager: KeyManager) -> None:
    global _bot, _scheduler, _config, _key_manager
    _bot = bot
    _scheduler = scheduler
    _config = config
    _key_manager = key_manager


def build_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1}
    )


def register_user_jobs(db_user: sqlite3.Row) -> None:
    """Идемпотентно (replace_existing) регистрирует утро/день для пользователя."""
    if _scheduler is None:
        return  # планировщик ещё не инициализирован (например, в тестах)
    try:
        tz = ZoneInfo(db_user["timezone"] or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    _scheduler.add_job(
        morning_job,
        CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=tz),
        id=f"morning_{db_user['id']}",
        args=(db_user["id"],),
        replace_existing=True,
    )
    _scheduler.add_job(
        midday_job,
        CronTrigger(hour=MIDDAY_HOUR, minute=MIDDAY_MINUTE, timezone=tz),
        id=f"midday_{db_user['id']}",
        args=(db_user["id"],),
        replace_existing=True,
    )


def register_all_users() -> None:
    for user in repo.get_all_users():
        register_user_jobs(user)


async def morning_job(user_id: int) -> None:
    try:
        await _morning_job(user_id)
    except Exception:
        logger.exception("morning_job failed for user %s", user_id)


async def _morning_job(user_id: int) -> None:
    from bot.handlers.tasks import render_task_list

    db_user = repo.get_user(user_id)
    if db_user is None or not has_access(db_user):
        return
    if not repo.list_active_goals(user_id):
        return

    today = today_local(db_user)

    # Идемпотентность: если задачи на сегодня уже есть — только показать их
    existing = repo.list_tasks_for_date(user_id, today)
    if not existing:
        try:
            client = orchestrator.build_client(db_user, _config, _key_manager)
        except orchestrator.ClientConfigError:
            logger.info("morning_job: user %s has no AI configured, skipping", user_id)
            return

        system_prompt = orchestrator.build_morning_system_prompt(db_user)
        try:
            raw = await client.send_message(
                [ChatMessage(role="user", content=prompts.MORNING_TRIGGER)],
                system_prompt=system_prompt,
            )
        except AIClientError:
            logger.exception("morning_job: AI call failed for user %s", user_id)
            return

        proposed = orchestrator.parse_morning_response(raw)
        if not proposed:
            logger.warning("morning_job: unparseable AI response for user %s", user_id)
            return

        for i, t in enumerate(proposed[:5]):
            title = t.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            goal_id = t.get("goal_id")
            if goal_id is not None and (
                not isinstance(goal_id, int) or not repo.goal_exists(user_id, goal_id)
            ):
                goal_id = None
            description = t.get("description")
            if not isinstance(description, str):
                description = None
            repo.add_task(
                user_id,
                title=title.strip()[:200],
                date=today,
                description=description,
                goal_id=goal_id,
                source="ai",
                order_index=i,
            )

    tasks = repo.list_tasks_for_date(user_id, today)
    if not tasks:
        return
    text, kb = render_task_list(tasks, texts.MORNING_HEADER)
    await _bot.send_message(db_user["telegram_id"], truncate(text), reply_markup=kb)


async def midday_job(user_id: int) -> None:
    try:
        await _midday_job(user_id)
    except Exception:
        logger.exception("midday_job failed for user %s", user_id)


async def _midday_job(user_id: int) -> None:
    import html

    db_user = repo.get_user(user_id)
    if db_user is None or not has_access(db_user):
        return

    today = today_local(db_user)
    repo.upsert_checkin_sent(user_id, today)

    text = texts.CHECKIN_QUESTION
    pending = [t for t in repo.list_tasks_for_date(user_id, today) if t["status"] == "pending"]
    if pending:
        task_lines = "\n".join(f"⬜ {html.escape(t['title'])}" for t in pending)
        text += texts.CHECKIN_PENDING_TASKS.format(tasks=task_lines)
    await _bot.send_message(db_user["telegram_id"], truncate(text))
