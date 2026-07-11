"""
bot/handlers/voice.py

Голосовые сообщения: скачивание → транскрибация (локальный faster-whisper) →
показ распознанного текста → общий текстовый AI-пайплайн (process_free_text).
"""
from __future__ import annotations

import html
import logging
import sqlite3

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from ai.key_manager import KeyManager
from ai.transcription import TranscriptionError, WhisperTranscriber
from bot import texts
from bot.config import MAX_VOICE_SECONDS, Config
from bot.handlers.ai_chat import process_free_text
from bot.utils import has_access, truncate

logger = logging.getLogger(__name__)
router = Router(name="voice")


@router.message(F.voice, StateFilter(None))
async def voice_message(
    message: Message,
    db_user: sqlite3.Row,
    config: Config,
    key_manager: KeyManager,
    transcriber: WhisperTranscriber,
) -> None:
    if not has_access(db_user):          # до скачивания и CPU-работы
        await message.answer(texts.NO_ACCESS)
        return
    if message.voice.duration > MAX_VOICE_SECONDS:
        await message.answer(texts.VOICE_TOO_LONG)
        return

    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            audio = await message.bot.download(message.voice)   # io.BytesIO
            text = await transcriber.transcribe(audio)
    except TranscriptionError:
        await message.answer(texts.VOICE_ERROR)
        return
    except Exception:                    # ошибки скачивания/сети
        logger.exception("Voice download failed")
        await message.answer(texts.VOICE_ERROR)
        return

    if not text:
        await message.answer(texts.VOICE_EMPTY)
        return

    await message.answer(truncate(texts.VOICE_RECOGNIZED.format(text=html.escape(text))))
    await process_free_text(message, db_user, text, config, key_manager)


@router.message(F.voice)                 # любое FSM-состояние ≠ None
async def voice_in_dialog(message: Message) -> None:
    await message.answer(texts.VOICE_IN_DIALOG)
