"""
bot/keyboards.py

CallbackData-фабрики и построители inline-клавиатур.
"""
from __future__ import annotations

import sqlite3

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts


class PendingActionCb(CallbackData, prefix="pa"):
    action: str        # "confirm" | "reject" | "edit"
    pa_id: int


class TaskCb(CallbackData, prefix="task"):
    action: str        # "done"
    task_id: int


class SetKeyCb(CallbackData, prefix="setkey"):
    field: str         # "prov"
    value: str         # "claude" | "ollama"


class ProviderCb(CallbackData, prefix="prov"):
    action: str        # "set"
    provider: str


def proposal_kb(pa_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_CONFIRM, callback_data=PendingActionCb(action="confirm", pa_id=pa_id))
    b.button(text=texts.BTN_REJECT, callback_data=PendingActionCb(action="reject", pa_id=pa_id))
    b.button(text=texts.BTN_EDIT, callback_data=PendingActionCb(action="edit", pa_id=pa_id))
    b.adjust(3)
    return b.as_markup()


def tasks_kb(tasks: list[sqlite3.Row]) -> InlineKeyboardMarkup | None:
    """Кнопка «✅ n» на каждую pending-задачу; None, если отмечать нечего."""
    b = InlineKeyboardBuilder()
    count = 0
    for i, task in enumerate(tasks, start=1):
        if task["status"] == "pending":
            b.button(text=f"✅ {i}", callback_data=TaskCb(action="done", task_id=task["id"]))
            count += 1
    if count == 0:
        return None
    b.adjust(8)
    return b.as_markup()


def setkey_provider_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Claude", callback_data=SetKeyCb(field="prov", value="claude"))
    b.button(text="Ollama (локальная)", callback_data=SetKeyCb(field="prov", value="ollama"))
    b.adjust(2)
    return b.as_markup()


def provider_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Claude", callback_data=ProviderCb(action="set", provider="claude"))
    b.button(text="Ollama (локальная)", callback_data=ProviderCb(action="set", provider="ollama"))
    b.adjust(2)
    return b.as_markup()
