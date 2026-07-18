"""
Тесты /settings: парсинг AI_MODELS, фильтр выполненных, выбор модели в build_client,
сеттеры настроек, сортировка прошлых задач.
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot import texts
from bot.config import MODELS_PER_PAGE, _parse_ai_models
from bot.handlers.tasks import render_task_list
from bot.services import repository as repo
from db.migrate import apply_migrations


# ── парсинг AI_MODELS ────────────────────────────────────────────

def test_parse_pairs_basic():
    r = _parse_ai_models("claude:claude-opus-4-8,ollama:qwen2.5:14b")
    assert [(m.provider, m.model) for m in r] == [
        ("claude", "claude-opus-4-8"),
        ("ollama", "qwen2.5:14b"),  # split по первому ':' сохраняет ':' в модели
    ]


def test_parse_multiple_same_provider():
    r = _parse_ai_models("claude:claude-opus-4-8,claude:claude-opus-4-7")
    assert len(r) == 2 and all(m.provider == "claude" for m in r)


def test_parse_drops_invalid():
    r = _parse_ai_models("bad, :nope, ollama:, unknown:model, claude:ok")
    assert [(m.provider, m.model) for m in r] == [("claude", "ok")]


def test_models_per_page_constant():
    assert MODELS_PER_PAGE == 5


# ── БД: настройки и фильтр ───────────────────────────────────────

@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")  # id=1
    conn.commit()
    conn.close()

    def _test_connect(_ignored=None):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON;")
        return c

    monkeypatch.setattr(repo, "_connect", _test_connect)
    return db_path


def test_show_completed_default_on(temp_db):
    assert repo.get_user(1)["show_completed_today"] == 1


def test_set_show_completed_today(temp_db):
    repo.set_show_completed_today(1, False)
    assert repo.get_user(1)["show_completed_today"] == 0
    repo.set_show_completed_today(1, True)
    assert repo.get_user(1)["show_completed_today"] == 1


def test_set_ai_model(temp_db):
    repo.set_ai_model(1, "claude-opus-4-7")
    assert repo.get_user(1)["ai_model"] == "claude-opus-4-7"


def test_filter_excludes_done(temp_db):
    repo.add_task(1, title="pending", date="2026-07-19")
    done = repo.add_task(1, title="done", date="2026-07-19")
    repo.mark_task_done(done, "2026-07-19")

    all_tasks = repo.list_tasks_for_date(1, "2026-07-19")
    visible = repo.list_tasks_for_date(1, "2026-07-19", include_done=False)
    assert len(all_tasks) == 2
    assert [t["title"] for t in visible] == ["pending"]


# ── build_client учитывает ai_model ──────────────────────────────

def test_build_client_uses_ai_model_for_claude(temp_db, monkeypatch):
    from bot.services import ai_orchestrator as orch

    repo.set_ai_provider(1, "claude")
    repo.set_ai_model(1, "claude-opus-4-7")

    class _KM:
        def get_active_key(self, uid, provider):
            return "sk-test"

    class _Cfg:
        ollama_host = "http://localhost:11434"

    client = orch.build_client(repo.get_user(1), _Cfg(), _KM())
    assert client.default_model == "claude-opus-4-7"


def test_build_client_ollama_fallback_to_ollama_model(temp_db):
    from bot.services import ai_orchestrator as orch

    repo.set_ai_provider(1, "ollama")
    repo.set_ollama_model(1, "llama3.1")   # ai_model не задан → фолбэк

    class _Cfg:
        ollama_host = "http://localhost:11434"

    client = orch.build_client(repo.get_user(1), _Cfg(), None)
    assert client.default_model == "llama3.1"


# ── сортировка прошлых задач (новые → старые) ────────────────────

def _task(id_, title, date, planned_date, status="pending"):
    return {
        "id": id_, "title": title, "date": date, "planned_date": planned_date,
        "status": status, "estimate_minutes": None,
    }


def test_past_sorted_newest_first():
    tasks = [
        _task(1, "сегодня", "2026-07-19", "2026-07-19"),
        _task(2, "старая", "2026-07-19", "2026-07-05"),
        _task(3, "вчерашняя", "2026-07-19", "2026-07-18"),
    ]
    text, _kb = render_task_list(tasks, texts.TODAY_HEADER)
    # среди «Прошлых» вчерашняя (18-е) идёт раньше старой (05-е)
    assert text.index("вчерашняя") < text.index("старая")
