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
from bot.keyboards import ProviderCb, aims_kb, provider_kb
from bot.services import repository as repo
from bot.services import scheduler as scheduler_service
from bot.states import SetCutoff, SetTimezone
from bot.utils import step_progress_suffix, today_local, truncate

router = Router(name="commands")


def render_goal_list(goals: list[sqlite3.Row]) -> str:
    lines = [texts.AIMS_HEADER]
    for i, g in enumerate(goals, start=1):
        meta = []
        if g["priority"]:
            meta.append(f"приоритет {g['priority']}")
        if g["target_date"]:
            meta.append(f"срок {html.escape(g['target_date'])}")
        suffix = f" — {', '.join(meta)}" if meta else ""
        lines.append(f"{i}. <b>{html.escape(g['title'])}</b>{suffix}")
        if g["description"]:
            lines.append(f"   <i>{html.escape(g['description'])}</i>")
        # текущий (первый невыполненный) шаг плана — «выучить японский → уроки (2/3)»
        step = repo.current_goal_step(g["id"])
        if step is not None:
            lines.append(
                f"   ▸ {html.escape(step['title'])}{step_progress_suffix(step)}"
            )
    return "\n".join(lines)


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
    repo.ensure_default_reminders(db_user["id"])  # новым — дефолтные времена
    scheduler_service.register_user_jobs(db_user)
    name = html.escape(db_user["first_name"] or "друг")
    await message.answer(texts.GREETING.format(name=name))
    if (db_user["timezone"] or "UTC") == "UTC":
        await message.answer(texts.TIMEZONE_HINT)


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
    today = today_local(db_user)
    tasks = repo.list_tasks_for_date(db_user["id"], today)
    if not tasks:
        note = texts.TODAY_EMPTY_TZ_NOTE.format(
            tz=html.escape(db_user["timezone"] or "UTC"), date=today
        )
        await message.answer(f"{texts.TODAY_EMPTY}\n\n{note}")
        return
    text, kb = render_task_list(tasks, texts.TODAY_HEADER)
    await message.answer(text, reply_markup=kb)


@router.message(Command("aims"))
async def cmd_aims(message: Message, db_user: sqlite3.Row) -> None:
    goals = repo.list_active_goals(db_user["id"])
    if not goals:
        await message.answer(texts.AIMS_EMPTY)
        return
    await message.answer(truncate(render_goal_list(goals)), reply_markup=aims_kb(goals))


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, state: FSMContext) -> None:
    await state.set_state(SetTimezone.waiting_for_tz)
    await message.answer(texts.TIMEZONE_ASK)


@router.message(Command("cutoff"))
async def cmd_cutoff(message: Message, state: FSMContext) -> None:
    await state.set_state(SetCutoff.waiting_for_hour)
    await message.answer(texts.CUTOFF_ASK)


@router.message(StateFilter(SetCutoff.waiting_for_hour), F.text)
async def cutoff_received(message: Message, state: FSMContext, db_user: sqlite3.Row) -> None:
    raw = message.text.strip()
    try:
        hour = int(raw)
    except ValueError:
        await message.answer(texts.CUTOFF_INVALID)
        return
    if not 0 <= hour <= 23:
        await message.answer(texts.CUTOFF_INVALID)
        return
    repo.set_planning_cutoff_hour(db_user["id"], hour)
    await state.clear()
    await message.answer(texts.CUTOFF_SAVED.format(hour=hour))


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
