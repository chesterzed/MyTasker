"""
bot/services/scheduler.py

APScheduler: на каждого пользователя — по одному cron-джобу на каждое его время
напоминания (таблица reminders) в его часовом поясе. Тон сообщения зависит от
позиции времени в списке и времени суток (см. _reminder_role). Ссылки на
bot/config/key_manager задаются из main.py через setup().
"""
from __future__ import annotations

import html
import logging
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ai.base import AIClientError, ChatMessage
from ai.key_manager import KeyManager
from bot import texts
from bot.config import EVENING_HOUR, Config
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
    """Полностью пересобирает cron-джобы напоминаний пользователя из таблицы reminders.

    Идемпотентно: снимает все прежние джобы пользователя и заводит по одному на
    каждое актуальное время. Вызывается на старте, при смене таймзоны и после
    любой правки списка напоминаний."""
    if _scheduler is None:
        return  # планировщик ещё не инициализирован (например, в тестах)
    try:
        tz = ZoneInfo(db_user["timezone"] or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    uid = db_user["id"]
    prefix = f"reminder_{uid}_"
    for job in _scheduler.get_jobs():
        if job.id.startswith(prefix):
            _scheduler.remove_job(job.id)

    for reminder in repo.list_reminders(uid):
        hour, minute = (int(part) for part in reminder["time"].split(":"))
        _scheduler.add_job(
            reminder_job,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=f"{prefix}{reminder['id']}",
            args=(reminder["id"],),
            replace_existing=True,
        )

    # Ночной перенос незакрытых задач на новый день (00:01 местного времени)
    _scheduler.add_job(
        rollover_job,
        CronTrigger(hour=0, minute=1, timezone=tz),
        id=f"rollover_{uid}",
        args=(uid,),
        replace_existing=True,
    )


def register_all_users() -> None:
    for user in repo.get_all_users():
        register_user_jobs(user)


def _reminder_role(times: list[str], index: int, evening_hour: int = EVENING_HOUR) -> str:
    """Роль напоминания по позиции в отсортированном списке времён и времени суток:
    'first' — первое за день (доброе утро + план);
    'progress' — не первое, дневное (< evening_hour);
    'deadline' — вечернее (>= evening_hour), но не последнее;
    'summary' — вечернее и последнее."""
    if index == 0:
        return "first"
    hour = int(times[index].split(":")[0])
    is_evening = hour >= evening_hour
    is_last = index == len(times) - 1
    if is_evening and is_last:
        return "summary"
    if is_evening:
        return "deadline"
    return "progress"


_CHECKIN_HEADERS = {
    "progress": texts.REMINDER_PROGRESS,
    "deadline": texts.REMINDER_DEADLINE,
    "summary": texts.REMINDER_SUMMARY,
}


async def rollover_job(user_id: int) -> None:
    try:
        await _rollover_job(user_id)
    except Exception:
        logger.exception("rollover_job failed for user %s", user_id)


async def _rollover_job(user_id: int) -> None:
    """00:01 местного времени: переносим просроченные незакрытые задачи на сегодня.
    Без сообщения пользователю — их покажет утреннее напоминание."""
    db_user = repo.get_user(user_id)
    if db_user is None:
        return
    moved = repo.roll_over_tasks(user_id, today_local(db_user))
    if moved:
        logger.info("rolled over %s tasks to today for user %s", moved, user_id)


async def reminder_job(reminder_id: int) -> None:
    try:
        await _reminder_job(reminder_id)
    except Exception:
        logger.exception("reminder_job failed for reminder %s", reminder_id)


async def _reminder_job(reminder_id: int) -> None:
    reminder = repo.get_reminder(reminder_id)
    if reminder is None:  # напоминание удалили — джоб мог остаться на лету
        return
    user_id = reminder["user_id"]
    db_user = repo.get_user(user_id)
    if db_user is None or not has_access(db_user):
        return

    reminders = repo.list_reminders(user_id)
    times = [r["time"] for r in reminders]
    try:
        index = next(i for i, r in enumerate(reminders) if r["id"] == reminder_id)
    except StopIteration:
        return

    role = _reminder_role(times, index)
    if role == "first":
        await _send_plan(db_user)
    else:
        await _send_checkin(db_user, _CHECKIN_HEADERS[role])


async def _send_plan(db_user: sqlite3.Row) -> None:
    """Первое напоминание за день: сгенерировать задачи (если ещё нет) и прислать план."""
    from bot.handlers.tasks import render_task_list

    user_id = db_user["id"]
    if not repo.list_active_goals(user_id):
        return

    today = today_local(db_user)
    existing = repo.list_tasks_for_date(user_id, today)
    if not existing:
        try:
            client = orchestrator.build_client(db_user, _config, _key_manager)
        except orchestrator.ClientConfigError:
            logger.info("reminder plan: user %s has no AI configured, skipping", user_id)
            return

        system_prompt = orchestrator.build_morning_system_prompt(db_user)
        try:
            raw = await client.send_message(
                [ChatMessage(role="user", content=prompts.MORNING_TRIGGER)],
                system_prompt=system_prompt,
            )
        except AIClientError:
            logger.exception("reminder plan: AI call failed for user %s", user_id)
            return

        proposed = orchestrator.parse_morning_response(raw)
        if not proposed:
            logger.warning("reminder plan: unparseable AI response for user %s", user_id)
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

    tasks = repo.list_tasks_for_date(
        user_id, today, include_done=bool(db_user["show_completed_today"])
    )
    if not tasks:
        return
    text, kb = render_task_list(tasks, texts.MORNING_HEADER)
    await _bot.send_message(db_user["telegram_id"], truncate(text), reply_markup=kb)


async def _send_checkin(db_user: sqlite3.Row, header: str) -> None:
    """Не первое напоминание: чек-ин выбранным тоном + список ещё не сделанных задач."""
    user_id = db_user["id"]
    today = today_local(db_user)
    repo.upsert_checkin_sent(user_id, today)

    text = header
    pending = [t for t in repo.list_tasks_for_date(user_id, today) if t["status"] == "pending"]
    if pending:
        task_lines = "\n".join(f"⬜ {html.escape(t['title'])}" for t in pending)
        text += texts.CHECKIN_PENDING_TASKS.format(tasks=task_lines)
    await _bot.send_message(db_user["telegram_id"], truncate(text))
