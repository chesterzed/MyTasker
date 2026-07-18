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


class SettingsCb(CallbackData, prefix="st"):
    action: str        # "root" | "visual" | "vis_toggle" | "model" | "pick" | "tz"
    arg: int = 0       # model: номер страницы; pick: индекс модели в config.ai_models


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


def settings_root_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SETTINGS_VISUAL, callback_data=SettingsCb(action="visual"))
    b.button(text=texts.BTN_SETTINGS_MODEL, callback_data=SettingsCb(action="model", arg=0))
    b.button(text=texts.BTN_SETTINGS_TZ, callback_data=SettingsCb(action="tz"))
    b.adjust(1)
    return b.as_markup()


def settings_visual_kb(show_completed: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SETTINGS_BACK, callback_data=SettingsCb(action="root"))
    mark = "✅" if show_completed else "⬜"
    b.button(
        text=f"{mark} {texts.BTN_SETTINGS_SHOW_COMPLETED}",
        callback_data=SettingsCb(action="vis_toggle"),
    )
    b.adjust(1)
    return b.as_markup()


def settings_model_kb(models: list, page: int, per_page: int) -> InlineKeyboardMarkup:
    """Кнопка «Назад» (в root) + до per_page моделей текущей страницы + ряд
    пагинации ◀️/▶️ (только доступные направления). callback pick.arg = глобальный
    индекс модели в списке config.ai_models."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SETTINGS_BACK, callback_data=SettingsCb(action="root"))
    start = page * per_page
    for gi in range(start, min(start + per_page, len(models))):
        b.button(
            text=models[gi].model, callback_data=SettingsCb(action="pick", arg=gi)
        )
    b.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="◀️", callback_data=SettingsCb(action="model", arg=page - 1))
    if start + per_page < len(models):
        nav.button(text="▶️", callback_data=SettingsCb(action="model", arg=page + 1))
    if nav.buttons:
        nav.adjust(2)
        b.attach(nav)
    return b.as_markup()


def settings_back_kb() -> InlineKeyboardMarkup:
    """Одна кнопка «Назад» в root — для экранов ввода (ключ / часовой пояс)."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SETTINGS_BACK, callback_data=SettingsCb(action="root"))
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
