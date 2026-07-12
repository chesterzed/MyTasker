"""
bot/handlers/tasks.py

Кнопки «✅ n» — отметить задачу выполненной, с перерисовкой списка на месте.
Также экспортирует render_task_list — общий рендер списка задач
(используется в /today, утренней рассылке и после нажатия кнопки).
"""
from __future__ import annotations

import html
import sqlite3

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from bot import texts
from bot.keyboards import TaskCb, tasks_kb
from bot.services import repository as repo

router = Router(name="tasks")

_STATUS_ICONS = {"pending": "⬜", "done": "✅", "skipped": "⏭", "moved": "📅"}


def render_task_list(
    tasks: list[sqlite3.Row], header: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    lines = [header]
    for i, task in enumerate(tasks, start=1):
        icon = _STATUS_ICONS.get(task["status"], "⬜")
        estimate = task["estimate_minutes"] if "estimate_minutes" in task.keys() else None
        suffix = f" · ~{estimate} мин" if estimate else ""
        lines.append(f"{icon} {i}. {html.escape(task['title'])}{suffix}")
    return "\n".join(lines), tasks_kb(tasks)


@router.callback_query(TaskCb.filter())
async def on_task_done(
    callback: CallbackQuery, callback_data: TaskCb, db_user: sqlite3.Row
) -> None:
    task = repo.get_task(callback_data.task_id)
    if task is None or task["user_id"] != db_user["id"]:
        await callback.answer(texts.STALE_PROPOSAL)
        return
    if task["status"] != "pending":
        await callback.answer(texts.TASK_ALREADY_DONE)
        return

    repo.mark_task_done(task["id"])

    # Перерисовать список в том же сообщении, сохранив его заголовок
    tasks = repo.list_tasks_for_date(db_user["id"], task["date"])
    header = texts.TODAY_HEADER
    if callback.message and callback.message.html_text:
        header = callback.message.html_text.split("\n")[0]
    text, kb = render_task_list(tasks, header)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass  # сообщение слишком старое или не изменилось — не критично
    await callback.answer(texts.TASK_DONE_ANSWER)
