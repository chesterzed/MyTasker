"""
ai/transcription.py

Локальная транскрибация голосовых через faster-whisper.
Один конкретный класс без ABC: бэкенд один; появится второй —
выделить интерфейс будет тривиально.
"""
from __future__ import annotations

import asyncio
import logging
from typing import BinaryIO

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Любая ошибка при декодировании/распознавании аудио."""


class WhisperTranscriber:
    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str | None = None,   # None → вывести: cpu→int8, иначе float16
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type or ("int8" if device == "cpu" else "float16")
        self._model = None                 # ленивая загрузка при первом голосовом
        self._lock = asyncio.Lock()        # сериализует загрузку и инференс

    async def transcribe(self, audio: BinaryIO) -> str:
        """Распознанный текст ("" если речи нет). Кидает TranscriptionError."""
        async with self._lock:
            try:
                return await asyncio.to_thread(self._transcribe_sync, audio)
            except Exception as exc:
                logger.exception("Voice transcription failed")
                raise TranscriptionError(str(exc)) from exc

    def _transcribe_sync(self, audio: BinaryIO) -> str:
        # Выполняется в worker-потоке: и загрузка модели, и инференс блокирующие.
        if self._model is None:
            from faster_whisper import WhisperModel   # ленивый тяжёлый импорт

            logger.info(
                "Loading whisper model %r (%s/%s) — первый запуск скачивает ~470 МБ",
                self.model_name, self.device, self.compute_type,
            )
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        # transcribe() возвращает ленивый генератор — вычитываем целиком здесь,
        # в worker-потоке, иначе CPU-работа утечёт в event loop
        segments, _info = self._model.transcribe(audio, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
