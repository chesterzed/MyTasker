"""
bot/handlers/addaim.py

/addaim — добавление цели через FSM. Если день ещё не закончился, сразу
подбираем по цели одну задачу на сегодня (нейросетью).
"""
from __future__ import annotations

import html
import sqlite3

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ai.key_manager import KeyManager
from bot import texts
from bot.config import Config
from bot.handlers.tasks import render_task_list
from bot.services import planning
from bot.services import repository as repo
from bot.states import AddAim
from bot.utils import has_access, today_local, truncate

router = Router(name="addaim")


@router.message(Command("addaim"))
async def cmd_addaim(message: Message, state: FSMContext) -> None:
    await state.set_state(AddAim.waiting_for_goal_text)
    await message.answer(texts.ADDAIM_ASK)


@router.message(StateFilter(AddAim.waiting_for_goal_text), F.text)
async def goal_text_received(
    message: Message,
    state: FSMContext,
    db_user: sqlite3.Row,
    config: Config,
    key_manager: KeyManager,
) -> None:
    raw = message.text.strip()
    first_line, _, rest = raw.partition("\n")
    title = first_line.strip()[:200]
    description = rest.strip() or None

    goal_id = repo.add_goal(db_user["id"], title=title, description=description)
    await state.clear()
    await message.answer(texts.ADDAIM_SAVED.format(title=html.escape(title)))

    # Если день ещё не закончился — сразу подберём одну задачу на сегодня.
    if not (has_access(db_user) and planning.has_time_left_today(db_user)):
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    added = await planning.generate_today_task_for_goal(
        db_user, goal_id, config, key_manager
    )
    if not added:
        return
    tasks = repo.list_tasks_for_date(db_user["id"], today_local(db_user))
    text, kb = render_task_list(tasks, texts.ADDAIM_TASKS_HEADER)
    await message.answer(truncate(text), reply_markup=kb)
