"""
Тесты хендлера голосовых (без скачивания модели — фейковый транскрайбер).
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ai.transcription import TranscriptionError, WhisperTranscriber
from bot import texts
from bot.handlers import voice as voice_handler


# ── заглушки ─────────────────────────────────────────────────────

class FakeTranscriber:
    def __init__(self, result: str = "распознанный текст", error: bool = False):
        self.result = result
        self.error = error
        self.called = False

    async def transcribe(self, audio) -> str:
        self.called = True
        if self.error:
            raise TranscriptionError("boom")
        return self.result


class FakeBot:
    # ChatActionSender читает bot.id (в логировании) и зовёт send_chat_action —
    # без них его worker умирает до установки _closed_event и __aexit__ виснет
    id = 123456

    async def download(self, voice):
        return b"fake-audio"

    async def send_chat_action(self, **kwargs):
        return None


class FakeMessage:
    def __init__(self, duration: int = 10):
        self.voice = SimpleNamespace(duration=duration)
        self.bot = FakeBot()
        self.chat = SimpleNamespace(id=1)
        self.answers: list[str] = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def make_user(role: str = "admin") -> dict:
    # sqlite3.Row поддерживает доступ по ключу — dict достаточно для has_access
    return {"id": 1, "role": role, "subscription_until": None}


@pytest.fixture()
def pipeline_recorder(monkeypatch):
    calls: list[str] = []

    async def fake_pipeline(message, db_user, text, config, key_manager):
        calls.append(text)

    monkeypatch.setattr(voice_handler, "process_free_text", fake_pipeline)
    return calls


def run(coro):
    return asyncio.run(coro)


# ── тесты хендлера ───────────────────────────────────────────────

def test_no_access_skips_transcription(pipeline_recorder):
    msg = FakeMessage()
    tr = FakeTranscriber()
    run(voice_handler.voice_message(msg, make_user(role="user"), None, None, tr))
    assert msg.answers == [texts.NO_ACCESS]
    assert not tr.called
    assert pipeline_recorder == []


def test_too_long_voice(pipeline_recorder):
    msg = FakeMessage(duration=301)
    tr = FakeTranscriber()
    run(voice_handler.voice_message(msg, make_user(), None, None, tr))
    assert msg.answers == [texts.VOICE_TOO_LONG]
    assert not tr.called


def test_happy_path(pipeline_recorder):
    msg = FakeMessage()
    tr = FakeTranscriber(result="сходить ко врачу завтра")
    run(voice_handler.voice_message(msg, make_user(), None, None, tr))
    assert len(msg.answers) == 1
    assert msg.answers[0].startswith("🎙 Распознано")
    assert "сходить ко врачу завтра" in msg.answers[0]
    assert pipeline_recorder == ["сходить ко врачу завтра"]


def test_empty_transcript(pipeline_recorder):
    msg = FakeMessage()
    tr = FakeTranscriber(result="")
    run(voice_handler.voice_message(msg, make_user(), None, None, tr))
    assert msg.answers == [texts.VOICE_EMPTY]
    assert pipeline_recorder == []


def test_transcription_error(pipeline_recorder):
    msg = FakeMessage()
    tr = FakeTranscriber(error=True)
    run(voice_handler.voice_message(msg, make_user(), None, None, tr))
    assert msg.answers == [texts.VOICE_ERROR]
    assert pipeline_recorder == []


def test_long_transcript_truncated(pipeline_recorder):
    msg = FakeMessage()
    tr = FakeTranscriber(result="ы" * 10000)
    run(voice_handler.voice_message(msg, make_user(), None, None, tr))
    assert len(msg.answers[0]) <= 4096


def test_voice_in_dialog():
    msg = FakeMessage()
    run(voice_handler.voice_in_dialog(msg))
    assert msg.answers == [texts.VOICE_IN_DIALOG]


# ── транскрайбер (без модели) ────────────────────────────────────

def test_compute_type_derived_cpu():
    assert WhisperTranscriber(device="cpu").compute_type == "int8"


def test_compute_type_derived_cuda():
    assert WhisperTranscriber(device="cuda").compute_type == "float16"


def test_compute_type_explicit():
    assert WhisperTranscriber(compute_type="float32").compute_type == "float32"
