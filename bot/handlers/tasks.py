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
from bot.utils import today_local


def _planned_note(task: sqlite3.Row) -> str:
    """« (изначально на DD.MM)», если задача переносилась (planned_date != date)."""
    planned = task["planned_date"] if "planned_date" in task.keys() else None
    if planned and planned != task["date"]:
        try:
            d = planned[8:10] + "." + planned[5:7]  # YYYY-MM-DD → DD.MM
        except (TypeError, IndexError):
            return ""
        return f" <i>(изначально на {d})</i>"
    return ""

router = Router(name="tasks")

_STATUS_ICONS = {"pending": "⬜", "done": "✅", "skipped": "⏭", "moved": "📅"}


def _is_priority(task: sqlite3.Row) -> bool:
    """Задача «на свой день»: активная дата совпадает с изначальной (или planned нет)."""
    planned = task["planned_date"] if "planned_date" in task.keys() else None
    return not planned or planned == task["date"]


def render_task_list(
    tasks: list[sqlite3.Row], header: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Список задач с разбивкой на «Приоритетные» (даты совпадают) и «Прошлые»
    (перенесены с прошлых дней). Текст и кнопки нумеруются по общему порядку
    ordered = приоритетные + прошлые, поэтому номера совпадают."""
    priority = [t for t in tasks if _is_priority(t)]
    past = [t for t in tasks if not _is_priority(t)]
    ordered = priority + past

    lines = [header]
    n = 0

    def emit(group: list[sqlite3.Row], label: str) -> None:
        nonlocal n
        if not group:
            return
        lines.append("")
        lines.append(label)
        for t in group:
            n += 1
            icon = _STATUS_ICONS.get(t["status"], "⬜")
            estimate = t["estimate_minutes"] if "estimate_minutes" in t.keys() else None
            est_s = f" · ~{estimate} мин" if estimate else ""
            lines.append(f"{icon} {n}. {html.escape(t['title'])}{est_s}{_planned_note(t)}")

    emit(priority, texts.TODAY_SECTION_PRIORITY)
    emit(past, texts.TODAY_SECTION_PAST)
    return "\n".join(lines), tasks_kb(ordered)


def render_all_tasks(tasks: list[sqlite3.Row], header: str) -> str:
    """Read-only сводка всех задач, сгруппированная по датам (без клавиатуры).

    tasks предполагаются отсортированными по date, order_index (см. list_all_tasks)."""
    lines = [header]
    current_date = None
    for task in tasks:
        if task["date"] != current_date:
            current_date = task["date"]
            lines.append(f"\n<b>{html.escape(current_date)}</b>")
        icon = _STATUS_ICONS.get(task["status"], "⬜")
        lines.append(f"{icon} {html.escape(task['title'])}{_planned_note(task)}")
    return "\n".join(lines)


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

    repo.mark_task_done(task["id"], today_local(db_user))

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
