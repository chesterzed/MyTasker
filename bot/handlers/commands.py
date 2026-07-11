"""
bot/handlers/commands.py

/start /help /cancel /today /timezone /provider
"""
from __future__ import annotations

import html
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.key_manager import KeyManager, KeyManagerError
from bot import texts
from bot.config import Config
from bot.handlers.tasks import render_task_list
from bot.keyboards import ProviderCb, provider_kb
from bot.services import repository as repo
from bot.services import scheduler as scheduler_service
from bot.states import SetTimezone
from bot.utils import today_local

router = Router(name="commands")


@router.message(Command("start"), StateFilter("*"))
async def cmd_start(
    message: Message, state: FSMContext, db_user: sqlite3.Row, config: Config
) -> None:
    await state.clear()
    if (
        config.admin_telegram_id is not None
        and db_user["telegram_id"] == config.admin_telegram_id
        and db_user["role"] != "admin"
    ):
        repo.set_role(db_user["id"], "admin")
    scheduler_service.register_user_jobs(db_user)
    name = html.escape(db_user["first_name"] or "друг")
    await message.answer(texts.GREETING.format(name=name))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.CANCELLED)


@router.message(Command("today"))
async def cmd_today(message: Message, db_user: sqlite3.Row) -> None:
    tasks = repo.list_tasks_for_date(db_user["id"], today_local(db_user))
    if not tasks:
        await message.answer(texts.TODAY_EMPTY)
        return
    text, kb = render_task_list(tasks, texts.TODAY_HEADER)
    await message.answer(text, reply_markup=kb)


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, state: FSMContext) -> None:
    await state.set_state(SetTimezone.waiting_for_tz)
    await message.answer(texts.TIMEZONE_ASK)


@router.message(StateFilter(SetTimezone.waiting_for_tz), F.text)
async def tz_received(message: Message, state: FSMContext, db_user: sqlite3.Row) -> None:
    tz_name = message.text.strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        await message.answer(texts.TIMEZONE_INVALID)
        return
    repo.set_timezone(db_user["id"], tz_name)
    await state.clear()
    scheduler_service.register_user_jobs(repo.get_user(db_user["id"]))
    await message.answer(texts.TIMEZONE_SAVED.format(tz=html.escape(tz_name)))


@router.message(Command("provider"))
async def cmd_provider(message: Message) -> None:
    await message.answer(texts.PROVIDER_CHOOSE, reply_markup=provider_kb())


@router.callback_query(ProviderCb.filter(F.action == "set"))
async def on_provider_set(
    callback: CallbackQuery,
    callback_data: ProviderCb,
    db_user: sqlite3.Row,
    key_manager: KeyManager,
) -> None:
    provider = callback_data.provider
    if provider == "claude":
        try:
            key_manager.get_active_key(db_user["id"], "claude")
        except KeyManagerError:
            await callback.answer(texts.PROVIDER_NEED_KEY, show_alert=True)
            return
    elif provider == "ollama" and not db_user["ollama_model"]:
        await callback.answer(texts.PROVIDER_NEED_MODEL, show_alert=True)
        return

    repo.set_ai_provider(db_user["id"], provider)
    label = "Claude" if provider == "claude" else f"Ollama ({db_user['ollama_model']})"
    await callback.message.edit_text(texts.PROVIDER_SET.format(provider=label))
    await callback.answer()
