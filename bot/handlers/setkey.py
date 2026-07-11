"""
bot/handlers/setkey.py

/setkey — настройка нейросети: для Claude — API-ключ (сообщение с ключом
удаляется из чата), для Ollama — имя локальной модели.
Выбор провайдера в /setkey также делает его активным.
"""
from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.key_manager import KeyManager
from bot import texts
from bot.keyboards import SetKeyCb, setkey_provider_kb
from bot.services import repository as repo
from bot.states import SetKey

router = Router(name="setkey")


@router.message(Command("setkey"))
async def cmd_setkey(message: Message, state: FSMContext) -> None:
    await state.set_state(SetKey.waiting_for_provider)
    await message.answer(texts.SETKEY_CHOOSE_PROVIDER, reply_markup=setkey_provider_kb())


@router.callback_query(SetKeyCb.filter(F.field == "prov"), StateFilter(SetKey.waiting_for_provider))
async def on_setkey_provider(
    callback: CallbackQuery, callback_data: SetKeyCb, state: FSMContext
) -> None:
    if callback_data.value == "claude":
        await state.set_state(SetKey.waiting_for_key)
        await callback.message.edit_text(texts.SETKEY_ASK_KEY)
    else:
        await state.set_state(SetKey.waiting_for_ollama_model)
        await callback.message.edit_text(texts.SETKEY_ASK_OLLAMA_MODEL)
    await callback.answer()


@router.message(StateFilter(SetKey.waiting_for_key), F.text)
async def key_received(
    message: Message,
    state: FSMContext,
    db_user: sqlite3.Row,
    key_manager: KeyManager,
) -> None:
    key_manager.store_key(db_user["id"], "claude", message.text.strip())
    repo.set_ai_provider(db_user["id"], "claude")
    await state.clear()
    try:
        await message.delete()
        await message.answer(texts.SETKEY_KEY_SAVED)
    except TelegramBadRequest:
        await message.answer(texts.SETKEY_KEY_SAVED_DELETE_FAILED)


@router.message(StateFilter(SetKey.waiting_for_ollama_model), F.text)
async def ollama_model_received(
    message: Message, state: FSMContext, db_user: sqlite3.Row
) -> None:
    model = message.text.strip()
    repo.set_ollama_model(db_user["id"], model)
    repo.set_ai_provider(db_user["id"], "ollama")
    await state.clear()
    await message.answer(texts.SETKEY_OLLAMA_SAVED.format(model=model))
