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
    action: str        # "apply" | "all" | "reject" | "edit"
    pa_id: int
    idx: int = -1      # индекс действия для "apply"; -1 для остальных


class TaskCb(CallbackData, prefix="task"):
    action: str        # "done"
    task_id: int


class SetKeyCb(CallbackData, prefix="setkey"):
    field: str         # "prov"
    value: str         # "claude" | "ollama"


class ProviderCb(CallbackData, prefix="prov"):
    action: str        # "set"
    provider: str


class NotifCb(CallbackData, prefix="notif"):
    action: str        # "add" | "edit" | "del"
    reminder_id: int = 0   # для edit/del; 0 для add


class GoalPlanCb(CallbackData, prefix="plan"):
    action: str        # "show" | "back" | "gen"
    goal_id: int


class StepCb(CallbackData, prefix="step"):
    action: str        # "toggle"
    step_id: int


def proposal_kb(
    pa_id: int, actions: list[dict], done: list[bool]
) -> InlineKeyboardMarkup | None:
    """Компактные кнопки «✅ n» на каждое ещё не применённое действие + управляющий ряд.

    None, если применять больше нечего (все действия закрыты)."""
    pending = [i for i, _ in enumerate(actions) if not (i < len(done) and done[i])]
    if not pending:
        return None

    b = InlineKeyboardBuilder()
    for i in pending:
        b.button(
            text=f"✅ {i + 1}",
            callback_data=PendingActionCb(action="apply", pa_id=pa_id, idx=i),
        )

    controls = InlineKeyboardBuilder()
    if len(pending) >= 2:
        controls.button(
            text=texts.BTN_CONFIRM_ALL, callback_data=PendingActionCb(action="all", pa_id=pa_id)
        )
    controls.button(
        text=texts.BTN_REJECT, callback_data=PendingActionCb(action="reject", pa_id=pa_id)
    )
    controls.button(
        text=texts.BTN_EDIT, callback_data=PendingActionCb(action="edit", pa_id=pa_id)
    )

    b.adjust(8)                      # номерные кнопки — строками по 8
    controls.adjust(3)               # управляющий ряд — до attach
    b.attach(controls)               # управляющие кнопки ниже
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


def notifications_kb(reminders: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    """На каждое напоминание ряд [❌ i][✏️ i]; внизу отдельный ряд [➕ Добавить]."""
    b = InlineKeyboardBuilder()
    for i, r in enumerate(reminders, start=1):
        b.button(text=f"❌ {i}", callback_data=NotifCb(action="del", reminder_id=r["id"]))
        b.button(text=f"✏️ {i}", callback_data=NotifCb(action="edit", reminder_id=r["id"]))
    b.button(text=texts.BTN_NOTIF_ADD, callback_data=NotifCb(action="add"))
    b.adjust(*([2] * len(reminders) + [1]))
    return b.as_markup()


def aims_kb(goals: list[sqlite3.Row]) -> InlineKeyboardMarkup | None:
    """Кнопки «n 📄» под списком целей — открыть план цели.
    Нумерация совпадает с нумерацией render_goal_list (тот же порядок списка)."""
    if not goals:
        return None
    b = InlineKeyboardBuilder()
    for i, goal in enumerate(goals, start=1):
        b.button(
            text=f"{i} 📄", callback_data=GoalPlanCb(action="show", goal_id=goal["id"])
        )
    b.adjust(8)
    return b.as_markup()


def plan_kb(goal_id: int, steps: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    """Клавиатура плана: тумблеры шагов + «Составить план» (если пусто) + «Назад».

    Для невыполненного шага кнопка «✅ n» (отметить), для выполненного — «❌ n»
    (снять отметку). Перерисовывается после каждого нажатия."""
    b = InlineKeyboardBuilder()
    for i, step in enumerate(steps, start=1):
        mark = "❌" if step["status"] == "done" else "✅"
        b.button(
            text=f"{mark} {i}", callback_data=StepCb(action="toggle", step_id=step["id"])
        )
    b.adjust(8)

    controls = InlineKeyboardBuilder()
    if not steps:
        controls.button(
            text=texts.BTN_PLAN_GEN, callback_data=GoalPlanCb(action="gen", goal_id=goal_id)
        )
    controls.button(
        text=texts.BTN_PLAN_BACK, callback_data=GoalPlanCb(action="back", goal_id=goal_id)
    )
    controls.adjust(2)
    b.attach(controls)
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
