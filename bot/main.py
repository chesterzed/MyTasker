"""
bot/main.py

Точка входа: конфиг, Bot, Dispatcher, роутеры, планировщик, polling.
"""
from __future__ import annotations

import logging
import ssl

import certifi
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
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
    BotCommand(command="aims", description="Текущие цели"),
    BotCommand(command="today", description="Задачи на сегодня"),
    BotCommand(command="setkey", description="Настроить нейросеть"),
    BotCommand(command="provider", description="Переключить нейросеть"),
    BotCommand(command="timezone", description="Часовой пояс"),
    BotCommand(command="cutoff", description="До какого часа планировать день"),
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

    # Если задан TELEGRAM_PROXY — весь трафик к api.telegram.org идёт через него
    # (aiohttp не использует системный/env-прокси автоматически, нужен явный).
    session = AiohttpSession(proxy=config.telegram_proxy) if config.telegram_proxy else None
    if config.telegram_proxy:
        logger.info("Telegram через прокси: %s", config.telegram_proxy)
        # aiogram при настройке прокси-коннектора теряет свой явный certifi-контекст
        # (aiohttp_socks.ProxyConnector создаётся без "ssl" и падает на дефолтный
        # OpenSSL-стор хоста, который может быть неполным/битым) — возвращаем вручную.
        try:
            session._connector_init["ssl"] = ssl.create_default_context(cafile=certifi.where())
        except AttributeError:
            logger.warning("Не удалось выставить SSL-контекст для прокси-сессии aiogram")

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
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

    # Меню команд — косметика: сбой сети здесь не должен ронять бота
    # (сам polling переживает сетевые ошибки и ретраится сам)
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except TelegramNetworkError:
        logger.warning(
            "Не удалось установить меню команд (сеть). Бот продолжит работу, "
            "меню обновится при следующем успешном запуске."
        )

    logger.info("AimTracker bot started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
