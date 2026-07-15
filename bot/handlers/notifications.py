"""
bot/handlers/notifications.py

/notifications — меню времён напоминаний: список + кнопки ❌/✏️ на каждое и ➕
для добавления. Правки пересобирают cron-джобы через scheduler.register_user_jobs.
"""
from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.keyboards import NotifCb, notifications_kb
from bot.services import repository as repo
from bot.services import scheduler as scheduler_service
from bot.states import Notifications

router = Router(name="notifications")


def _render_menu(reminders: list[sqlite3.Row]) -> str:
    if not reminders:
        return texts.NOTIF_EMPTY
    lines = [texts.NOTIF_HEADER]
    for i, r in enumerate(reminders, start=1):
        lines.append(f"{i}. {r['time']}")
    return "\n".join(lines)


async def _show_menu(message: Message, user_id: int) -> None:
    reminders = repo.list_reminders(user_id)
    await message.answer(_render_menu(reminders), reply_markup=notifications_kb(reminders))


async def _rerender(callback: CallbackQuery, user_id: int) -> None:
    reminders = repo.list_reminders(user_id)
    try:
        await callback.message.edit_text(
            _render_menu(reminders), reply_markup=notifications_kb(reminders)
        )
    except TelegramBadRequest:
        pass


@router.message(Command("notifications"))
async def cmd_notifications(message: Message, db_user: sqlite3.Row) -> None:
    await _show_menu(message, db_user["id"])


@router.callback_query(NotifCb.filter(F.action == "del"))
async def on_delete(
    callback: CallbackQuery, callback_data: NotifCb, db_user: sqlite3.Row
) -> None:
    repo.delete_reminder(db_user["id"], callback_data.reminder_id)
    scheduler_service.register_user_jobs(repo.get_user(db_user["id"]))
    await _rerender(callback, db_user["id"])
    await callback.answer(texts.NOTIF_DELETED)


@router.callback_query(NotifCb.filter(F.action == "add"))
async def on_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Notifications.waiting_for_new_time)
    await callback.message.answer(texts.NOTIF_ASK_TIME)
    await callback.answer()


@router.callback_query(NotifCb.filter(F.action == "edit"))
async def on_edit(
    callback: CallbackQuery, callback_data: NotifCb, state: FSMContext
) -> None:
    await state.set_state(Notifications.waiting_for_edit_time)
    await state.update_data(reminder_id=callback_data.reminder_id)
    await callback.message.answer(texts.NOTIF_ASK_TIME)
    await callback.answer()


@router.message(StateFilter(Notifications.waiting_for_new_time), F.text)
async def new_time_received(
    message: Message, state: FSMContext, db_user: sqlite3.Row
) -> None:
    from bot.utils import parse_hhmm

    time = parse_hhmm(message.text)
    if time is None:
        await message.answer(texts.NOTIF_INVALID_TIME)
        return
    if any(r["time"] == time for r in repo.list_reminders(db_user["id"])):
        await message.answer(texts.NOTIF_DUPLICATE)
        return
    repo.add_reminder(db_user["id"], time)
    await state.clear()
    scheduler_service.register_user_jobs(repo.get_user(db_user["id"]))
    await _show_menu(message, db_user["id"])


@router.message(StateFilter(Notifications.waiting_for_edit_time), F.text)
async def edit_time_received(
    message: Message, state: FSMContext, db_user: sqlite3.Row
) -> None:
    from bot.utils import parse_hhmm

    time = parse_hhmm(message.text)
    if time is None:
        await message.answer(texts.NOTIF_INVALID_TIME)
        return
    data = await state.get_data()
    reminder_id = data.get("reminder_id")
    existing = repo.list_reminders(db_user["id"])
    if any(r["time"] == time and r["id"] != reminder_id for r in existing):
        await message.answer(texts.NOTIF_DUPLICATE)
        return
    repo.update_reminder(db_user["id"], reminder_id, time)
    await state.clear()
    scheduler_service.register_user_jobs(repo.get_user(db_user["id"]))
    await _show_menu(message, db_user["id"])
