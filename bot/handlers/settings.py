"""
bot/handlers/settings.py

/settings — меню настроек с навигацией по под-экранам (Визуал / Модель /
Часовой пояс) через редактирование одного сообщения. Ввод текста (API-ключ,
часовой пояс) — через FSM, как в notifications.py.
"""
from __future__ import annotations

import html
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.key_manager import KeyManager
from bot import texts
from bot.config import MODELS_PER_PAGE, Config
from bot.keyboards import (
    SettingsCb,
    settings_back_kb,
    settings_model_kb,
    settings_root_kb,
    settings_visual_kb,
)
from bot.services import repository as repo
from bot.services import scheduler as scheduler_service
from bot.states import Settings

router = Router(name="settings")


def _render_root(db_user: sqlite3.Row) -> str:
    show = db_user["show_completed_today"]
    model = db_user["ai_model"] or db_user["ai_provider"]
    return texts.SETTINGS_HEADER.format(
        show_completed=texts.SETTINGS_ON if show else texts.SETTINGS_OFF,
        model=html.escape(str(model)),
        tz=html.escape(db_user["timezone"] or "UTC"),
    )


async def _edit(callback: CallbackQuery, text: str, kb) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass  # текст не изменился / сообщение устарело


@router.message(Command("settings"), StateFilter("*"))
async def cmd_settings(message: Message, state: FSMContext, db_user: sqlite3.Row) -> None:
    await state.clear()
    await message.answer(_render_root(db_user), reply_markup=settings_root_kb())


@router.callback_query(SettingsCb.filter(F.action == "root"))
async def on_root(
    callback: CallbackQuery, db_user: sqlite3.Row, state: FSMContext
) -> None:
    await state.clear()  # на случай возврата с экрана ввода ключа/зоны
    await _edit(callback, _render_root(db_user), settings_root_kb())
    await callback.answer()


# ── Визуал ───────────────────────────────────────────────────────

@router.callback_query(SettingsCb.filter(F.action == "visual"))
async def on_visual(callback: CallbackQuery, db_user: sqlite3.Row) -> None:
    await _edit(
        callback,
        texts.SETTINGS_VISUAL_HEADER,
        settings_visual_kb(bool(db_user["show_completed_today"])),
    )
    await callback.answer()


@router.callback_query(SettingsCb.filter(F.action == "vis_toggle"))
async def on_visual_toggle(callback: CallbackQuery, db_user: sqlite3.Row) -> None:
    new_value = not bool(db_user["show_completed_today"])
    repo.set_show_completed_today(db_user["id"], new_value)
    await _edit(callback, texts.SETTINGS_VISUAL_HEADER, settings_visual_kb(new_value))
    await callback.answer()


# ── Модель ───────────────────────────────────────────────────────

@router.callback_query(SettingsCb.filter(F.action == "model"))
async def on_model(
    callback: CallbackQuery, callback_data: SettingsCb, config: Config
) -> None:
    models = list(config.ai_models)
    page = max(0, callback_data.arg)
    await _edit(
        callback,
        texts.SETTINGS_MODEL_HEADER,
        settings_model_kb(models, page, MODELS_PER_PAGE),
    )
    await callback.answer()


@router.callback_query(SettingsCb.filter(F.action == "pick"))
async def on_model_pick(
    callback: CallbackQuery,
    callback_data: SettingsCb,
    db_user: sqlite3.Row,
    config: Config,
    state: FSMContext,
) -> None:
    models = config.ai_models
    idx = callback_data.arg
    if idx < 0 or idx >= len(models):
        await callback.answer(texts.STALE_PROPOSAL)
        return
    entry = models[idx]

    if entry.provider == "ollama":
        # без ключа — активируем сразу
        repo.set_ai_provider(db_user["id"], "ollama")
        repo.set_ai_model(db_user["id"], entry.model)
        fresh = repo.get_user(db_user["id"])
        await _edit(
            callback,
            _render_root(fresh) + "\n\n" + texts.SETTINGS_MODEL_ACTIVE.format(
                model=html.escape(entry.model)
            ),
            settings_root_kb(),
        )
        await callback.answer()
        return

    # claude — просим ключ; провайдер/модель коммитим только после ввода ключа
    await state.set_state(Settings.waiting_for_key)
    await state.update_data(model=entry.model)
    await _edit(
        callback,
        texts.SETTINGS_ASK_KEY.format(model=html.escape(entry.model)),
        settings_back_kb(),
    )
    await callback.answer()


@router.message(StateFilter(Settings.waiting_for_key), F.text)
async def key_received(
    message: Message,
    state: FSMContext,
    db_user: sqlite3.Row,
    key_manager: KeyManager,
) -> None:
    data = await state.get_data()
    model = data.get("model", "")
    key_manager.store_key(db_user["id"], "claude", message.text.strip())
    repo.set_ai_provider(db_user["id"], "claude")
    repo.set_ai_model(db_user["id"], model)
    await state.clear()

    saved = texts.SETTINGS_KEY_SAVED.format(model=html.escape(model))
    try:
        await message.delete()
    except TelegramBadRequest:
        saved = texts.SETTINGS_KEY_SAVED_DELETE_FAILED.format(model=html.escape(model))
    fresh = repo.get_user(db_user["id"])
    await message.answer(
        _render_root(fresh) + "\n\n" + saved, reply_markup=settings_root_kb()
    )


# ── Часовой пояс ─────────────────────────────────────────────────

@router.callback_query(SettingsCb.filter(F.action == "tz"))
async def on_tz(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Settings.waiting_for_tz)
    await _edit(callback, texts.TIMEZONE_ASK, settings_back_kb())
    await callback.answer()


@router.message(StateFilter(Settings.waiting_for_tz), F.text)
async def tz_received(
    message: Message, state: FSMContext, db_user: sqlite3.Row
) -> None:
    tz_name = message.text.strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        await message.answer(texts.TIMEZONE_INVALID)
        return
    repo.set_timezone(db_user["id"], tz_name)
    await state.clear()
    scheduler_service.register_user_jobs(repo.get_user(db_user["id"]))
    fresh = repo.get_user(db_user["id"])
    await message.answer(
        _render_root(fresh) + "\n\n" + texts.SETTINGS_TZ_SAVED.format(tz=html.escape(tz_name)),
        reply_markup=settings_root_kb(),
    )
