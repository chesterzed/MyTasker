"""
bot/handlers/plans.py

Просмотр и правка плана цели: кнопки «n 📄» под /aims открывают план
(сообщение редактируется на месте), тумблеры «✅ n»/«❌ n» отмечают шаги,
«⬅️ Назад» возвращает список целей, «🪄 Составить план» — генерация нейросетью.
"""
from __future__ import annotations

import html
import logging
import sqlite3

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from ai.key_manager import KeyManager
from bot import texts
from bot.config import Config
from bot.keyboards import GoalPlanCb, StepCb, aims_kb, plan_kb
from bot.services import planning
from bot.services import repository as repo
from bot.utils import has_access, step_progress_suffix, truncate

logger = logging.getLogger(__name__)
router = Router(name="plans")


def render_plan(goal: sqlite3.Row, steps: list[sqlite3.Row]) -> str:
    lines = [texts.PLAN_HEADER.format(title=html.escape(goal["title"]))]
    if not steps:
        lines.append(texts.PLAN_EMPTY)
    for i, step in enumerate(steps, start=1):
        mark = "✅" if step["status"] == "done" else "⬜"
        lines.append(
            f"{mark} {i}. {html.escape(step['title'])}{step_progress_suffix(step)}"
        )
    return "\n".join(lines)


async def _show_plan(callback: CallbackQuery, goal: sqlite3.Row) -> None:
    steps = repo.list_goal_steps(goal["id"])
    try:
        await callback.message.edit_text(
            truncate(render_plan(goal, steps)), reply_markup=plan_kb(goal["id"], steps)
        )
    except TelegramBadRequest:
        pass  # текст не изменился или сообщение слишком старое


@router.callback_query(GoalPlanCb.filter(F.action == "show"))
async def on_plan_show(
    callback: CallbackQuery, callback_data: GoalPlanCb, db_user: sqlite3.Row
) -> None:
    goal = repo.get_goal(db_user["id"], callback_data.goal_id)
    if goal is None:
        await callback.answer(texts.STALE_PROPOSAL)
        return
    await _show_plan(callback, goal)
    await callback.answer()


@router.callback_query(GoalPlanCb.filter(F.action == "back"))
async def on_plan_back(
    callback: CallbackQuery, callback_data: GoalPlanCb, db_user: sqlite3.Row
) -> None:
    from bot.handlers.commands import render_goal_list  # deferred: без цикла импортов

    goals = repo.list_active_goals(db_user["id"])
    text = texts.AIMS_EMPTY if not goals else render_goal_list(goals)
    try:
        await callback.message.edit_text(truncate(text), reply_markup=aims_kb(goals))
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(StepCb.filter(F.action == "toggle"))
async def on_step_toggle(
    callback: CallbackQuery, callback_data: StepCb, db_user: sqlite3.Row
) -> None:
    step = repo.get_step(callback_data.step_id)
    if step is None or step["user_id"] != db_user["id"]:
        await callback.answer(texts.STALE_PROPOSAL)
        return

    if step["status"] == "done":
        repo.set_step_status(step["id"], "pending")
        answer = texts.STEP_UNDONE_ANSWER
    else:
        repo.set_step_status(step["id"], "done")
        answer = texts.STEP_DONE_ANSWER

    goal = repo.get_goal(db_user["id"], step["goal_id"])
    if goal is not None:
        await _show_plan(callback, goal)
    await callback.answer(answer)


@router.callback_query(GoalPlanCb.filter(F.action == "gen"))
async def on_plan_gen(
    callback: CallbackQuery,
    callback_data: GoalPlanCb,
    db_user: sqlite3.Row,
    config: Config,
    key_manager: KeyManager,
) -> None:
    goal = repo.get_goal(db_user["id"], callback_data.goal_id)
    if goal is None:
        await callback.answer(texts.STALE_PROPOSAL)
        return
    if not has_access(db_user):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_text(texts.PLAN_GENERATING, reply_markup=None)
    except TelegramBadRequest:
        pass

    count = await planning.generate_plan_for_goal(
        db_user, goal["id"], config, key_manager
    )
    if count == 0:
        steps = repo.list_goal_steps(goal["id"])
        try:
            await callback.message.edit_text(
                texts.PLAN_GEN_FAILED, reply_markup=plan_kb(goal["id"], steps)
            )
        except TelegramBadRequest:
            pass
        return
    await _show_plan(callback, goal)
