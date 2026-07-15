"""
bot/handlers/ai_chat.py

Ядро бота: свободный текст → нейросеть → ответ или предложение действий
с кнопками подтверждения. Роутер подключается ПОСЛЕДНИМ.

process_free_text() вынесена отдельно от aiogram-обёртки — это точка
расширения для будущих голосовых сообщений (транскрибация → тот же пайплайн).
"""
from __future__ import annotations

import html
import logging
import sqlite3

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from ai.base import (
    AIAuthError,
    AIClientError,
    AIRateLimitError,
    AITimeoutError,
    ChatMessage,
)
from ai.key_manager import KeyManager
from bot import texts
from bot.config import Config
from bot.keyboards import aims_kb, proposal_kb
from bot.services import actions as actions_service
from bot.services import ai_orchestrator as orchestrator
from bot.services import queries as queries_service
from bot.services import repository as repo
from bot.utils import has_access, today_local, truncate

logger = logging.getLogger(__name__)
router = Router(name="ai_chat")


async def _run_query(message: Message, db_user: sqlite3.Row, query: dict) -> None:
    """Выполнить read-запрос и показать список (диспатч по query['name'])."""
    # deferred-импорт форматтеров — как в scheduler, чтобы не плодить циклы
    from bot.handlers.commands import render_goal_list
    from bot.handlers.tasks import render_all_tasks, render_task_list

    name = query["name"]
    if name == "list_tasks":
        date = query["date"]
        tasks = repo.list_tasks_for_date(db_user["id"], date)
        if not tasks:
            await message.answer(texts.TASKS_ON_DATE_EMPTY.format(date=html.escape(date)))
            return
        text, kb = render_task_list(
            tasks, texts.TASKS_ON_DATE_HEADER.format(date=html.escape(date))
        )
        await message.answer(truncate(text), reply_markup=kb)
    elif name == "list_all_tasks":
        tasks = repo.list_all_tasks(db_user["id"])
        await message.answer(
            texts.ALL_TASKS_EMPTY
            if not tasks
            else truncate(render_all_tasks(tasks, texts.ALL_TASKS_HEADER))
        )
    elif name == "list_goals":
        goals = repo.list_active_goals(db_user["id"])
        if not goals:
            await message.answer(texts.AIMS_EMPTY)
        else:
            await message.answer(
                truncate(render_goal_list(goals)), reply_markup=aims_kb(goals)
            )


async def deliver_ai_response(
    message: Message, db_user: sqlite3.Row, raw: str, source_text: str
) -> None:
    """Общий хвост пайплайна: парсинг ответа модели → read-запросы (сразу),
    затем либо обычный ответ, либо предложение действий с кнопками.
    Используется и чатом, и правкой."""
    parsed = orchestrator.parse_ai_response(raw)

    # read-only запросы показываем сразу, без подтверждения
    for query in queries_service.validate_queries(parsed.queries, db_user):
        await _run_query(message, db_user, query)

    valid_actions = actions_service.validate_actions(parsed.actions, db_user["id"])

    if not valid_actions:
        if parsed.reply:  # не слать пустое сообщение, если показали только список
            await message.answer(truncate(html.escape(parsed.reply)))
        repo.log_message(
            db_user["id"], "assistant", orchestrator.assistant_turn_json(parsed.reply, [])
        )
        return

    type_ = valid_actions[0]["type"] if len(valid_actions) == 1 else "bulk_add"
    payload = {
        "actions": valid_actions,
        "reply": parsed.reply,
        "source_text": source_text,
        "done": [False] * len(valid_actions),
    }
    pa_id = repo.create_pending_action(db_user["id"], type_, payload)

    text = actions_service.render_proposal_text(payload)
    kb = proposal_kb(pa_id, valid_actions, payload["done"])
    sent = await message.answer(truncate(text), reply_markup=kb)
    repo.set_pending_message_id(pa_id, sent.message_id)

    repo.log_message(
        db_user["id"],
        "assistant",
        orchestrator.assistant_turn_json(parsed.reply, valid_actions),
    )


async def run_ai_request(
    message: Message,
    db_user: sqlite3.Row,
    config: Config,
    key_manager: KeyManager,
    history: list[ChatMessage],
    system_prompt: str,
) -> str | None:
    """Вызов модели с обработкой всех ошибок; None = ошибка уже показана."""
    try:
        client = orchestrator.build_client(db_user, config, key_manager)
    except orchestrator.ClientConfigError:
        await message.answer(texts.NO_KEY_HINT)
        return None

    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            return await client.send_message(history, system_prompt=system_prompt)
    except AIAuthError:
        await message.answer(texts.AI_AUTH_ERROR)
    except AIRateLimitError:
        await message.answer(texts.AI_RATE_LIMIT)
    except AITimeoutError:
        await message.answer(texts.AI_TIMEOUT)
    except AIClientError:
        logger.exception("AI request failed for user %s", db_user["id"])
        await message.answer(texts.AI_GENERIC_ERROR)
    return None


async def process_free_text(
    message: Message,
    db_user: sqlite3.Row,
    text: str,
    config: Config,
    key_manager: KeyManager,
) -> None:
    if not has_access(db_user):
        await message.answer(texts.NO_ACCESS)
        return

    repo.log_message(db_user["id"], "user", text)

    checkin = repo.get_open_checkin(db_user["id"], today_local(db_user))
    if checkin is not None:
        repo.save_checkin_response(checkin["id"], text)

    system_prompt = orchestrator.build_chat_system_prompt(
        db_user, checkin_active=checkin is not None
    )
    history = orchestrator.build_history(db_user["id"])

    raw = await run_ai_request(message, db_user, config, key_manager, history, system_prompt)
    if raw is not None:
        await deliver_ai_response(message, db_user, raw, source_text=text)


@router.message(F.text.startswith("/"), StateFilter(None))
async def unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND)


@router.message(F.text, StateFilter(None))
async def free_text(
    message: Message, db_user: sqlite3.Row, config: Config, key_manager: KeyManager
) -> None:
    await process_free_text(message, db_user, message.text, config, key_manager)
