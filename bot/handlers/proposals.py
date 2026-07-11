"""
bot/handlers/proposals.py

Кнопки под сообщением-предложением: Подтвердить / Отклонить / Изменить.
«Изменить» переводит в FSM-ожидание правки, после которой модель формирует
новое предложение (старое помечается отклонённым).
"""
from __future__ import annotations

import json
import logging
import sqlite3

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai.base import ChatMessage
from ai.key_manager import KeyManager
from bot import texts
from bot.config import Config
from bot.keyboards import PendingActionCb
from bot.services import actions as actions_service
from bot.services import ai_orchestrator as orchestrator
from bot.services import prompts
from bot.services import repository as repo
from bot.states import EditProposal
from bot.utils import truncate

logger = logging.getLogger(__name__)
router = Router(name="proposals")


def _load_valid_pending(pa_id: int, db_user: sqlite3.Row, expected_status: str):
    pa = repo.get_pending_action(pa_id)
    if pa is None or pa["user_id"] != db_user["id"] or pa["status"] != expected_status:
        return None
    return pa


async def _edit_source_message(
    callback: CallbackQuery, suffix: str, keep_keyboard: bool = False
) -> None:
    try:
        base = callback.message.html_text or ""
        await callback.message.edit_text(
            truncate(f"{base}\n\n{suffix}"),
            reply_markup=callback.message.reply_markup if keep_keyboard else None,
        )
    except TelegramBadRequest:
        pass


@router.callback_query(PendingActionCb.filter(F.action == "confirm"))
async def on_confirm(
    callback: CallbackQuery, callback_data: PendingActionCb, db_user: sqlite3.Row
) -> None:
    pa = _load_valid_pending(callback_data.pa_id, db_user, "pending")
    if pa is None:
        await callback.answer(texts.STALE_PROPOSAL)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        return

    payload = json.loads(pa["payload"])
    results = actions_service.apply_all(db_user["id"], payload["actions"])
    repo.resolve_pending(pa["id"], "confirmed")

    await _edit_source_message(callback, texts.PROPOSAL_APPLIED + ":\n" + "\n".join(results))
    await callback.answer()


@router.callback_query(PendingActionCb.filter(F.action == "reject"))
async def on_reject(
    callback: CallbackQuery, callback_data: PendingActionCb, db_user: sqlite3.Row
) -> None:
    pa = _load_valid_pending(callback_data.pa_id, db_user, "pending")
    if pa is None:
        await callback.answer(texts.STALE_PROPOSAL)
        return
    repo.resolve_pending(pa["id"], "rejected")
    await _edit_source_message(callback, texts.PROPOSAL_REJECTED)
    await callback.answer()


@router.callback_query(PendingActionCb.filter(F.action == "edit"))
async def on_edit(
    callback: CallbackQuery,
    callback_data: PendingActionCb,
    db_user: sqlite3.Row,
    state: FSMContext,
) -> None:
    pa = _load_valid_pending(callback_data.pa_id, db_user, "pending")
    if pa is None:
        await callback.answer(texts.STALE_PROPOSAL)
        return
    repo.set_pending_status(pa["id"], "editing")
    await state.set_state(EditProposal.waiting_for_correction)
    await state.update_data(pa_id=pa["id"])
    await _edit_source_message(callback, texts.PROPOSAL_EDIT_ASK)
    await callback.answer()


@router.message(StateFilter(EditProposal.waiting_for_correction), F.text)
async def correction_received(
    message: Message,
    state: FSMContext,
    db_user: sqlite3.Row,
    config: Config,
    key_manager: KeyManager,
) -> None:
    from bot.handlers.ai_chat import deliver_ai_response, run_ai_request

    data = await state.get_data()
    await state.clear()

    pa = _load_valid_pending(data.get("pa_id", -1), db_user, "editing")
    if pa is None:
        await message.answer(texts.STALE_PROPOSAL)
        return

    payload = json.loads(pa["payload"])
    correction = message.text
    repo.log_message(db_user["id"], "user", f"[правка предложения] {correction}")

    # История + старое предложение + правка → новый полный набор действий
    history = orchestrator.build_history(db_user["id"])
    history.append(
        ChatMessage(role="assistant", content=json.dumps(payload, ensure_ascii=False))
    )
    history.append(
        ChatMessage(role="user", content=prompts.REVISION_INSTRUCTION.format(correction=correction))
    )
    system_prompt = orchestrator.build_chat_system_prompt(db_user)

    raw = await run_ai_request(message, db_user, config, key_manager, history, system_prompt)
    if raw is None:
        return

    repo.resolve_pending(pa["id"], "rejected")  # старое предложение вытеснено новым
    await deliver_ai_response(
        message, db_user, raw, source_text=payload.get("source_text", correction)
    )
