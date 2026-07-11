"""
bot/handlers/addaim.py

/addaim — добавление цели через FSM.
"""
from __future__ import annotations

import html
import sqlite3

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import texts
from bot.services import repository as repo
from bot.states import AddAim

router = Router(name="addaim")


@router.message(Command("addaim"))
async def cmd_addaim(message: Message, state: FSMContext) -> None:
    await state.set_state(AddAim.waiting_for_goal_text)
    await message.answer(texts.ADDAIM_ASK)


@router.message(StateFilter(AddAim.waiting_for_goal_text), F.text)
async def goal_text_received(
    message: Message, state: FSMContext, db_user: sqlite3.Row
) -> None:
    raw = message.text.strip()
    first_line, _, rest = raw.partition("\n")
    title = first_line.strip()[:200]
    description = rest.strip() or None

    repo.add_goal(db_user["id"], title=title, description=description)
    await state.clear()
    await message.answer(texts.ADDAIM_SAVED.format(title=html.escape(title)))
