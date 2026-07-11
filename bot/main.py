"""
bot/main.py

Точка входа: конфиг, Bot, Dispatcher, роутеры, планировщик, polling.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from ai.key_manager import KeyManager
from ai.transcription import WhisperTranscriber
from bot.config import Config
from bot.fsm_storage import SQLiteFSMStorage
from bot.handlers import build_root_router
from bot.middlewares import UserMiddleware
from bot.services import scheduler as scheduler_service
from db.init_db import init_db

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Приветствие и регистрация"),
    BotCommand(command="addaim", description="Добавить цель"),
    BotCommand(command="today", description="Задачи на сегодня"),
    BotCommand(command="setkey", description="Настроить нейросеть"),
    BotCommand(command="provider", description="Переключить нейросеть"),
    BotCommand(command="timezone", description="Часовой пояс"),
    BotCommand(command="cancel", description="Отменить текущий диалог"),
    BotCommand(command="help", description="Справка"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.load()
    init_db()  # идемпотентно

    key_manager = KeyManager(master_key=config.fernet_master_key)
    transcriber = WhisperTranscriber(
        model_name=config.whisper_model, device=config.whisper_device
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=SQLiteFSMStorage())
    dp["config"] = config
    dp["key_manager"] = key_manager
    dp["transcriber"] = transcriber

    user_middleware = UserMiddleware()
    dp.message.outer_middleware(user_middleware)
    dp.callback_query.outer_middleware(user_middleware)

    dp.include_router(build_root_router())

    scheduler = scheduler_service.build_scheduler()
    scheduler_service.setup(bot, scheduler, config, key_manager)
    scheduler_service.register_all_users()
    scheduler.start()

    await bot.set_my_commands(BOT_COMMANDS)

    logger.info("AimTracker bot started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
