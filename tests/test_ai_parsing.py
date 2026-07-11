"""
Тесты парсинга ответов модели и валидации действий.
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.services import actions as actions_service
from bot.services import repository as repo
from bot.services.ai_orchestrator import parse_ai_response, parse_morning_response


# ── parse_ai_response ────────────────────────────────────────────

def test_plain_text_becomes_reply():
    parsed = parse_ai_response("Просто текст без JSON")
    assert parsed.reply == "Просто текст без JSON"
    assert parsed.actions == []


def test_valid_json():
    raw = '{"reply": "Привет!", "actions": []}'
    parsed = parse_ai_response(raw)
    assert parsed.reply == "Привет!"
    assert parsed.actions == []


def test_json_with_actions():
    raw = '{"reply": "Добавляю", "actions": [{"type": "add_task", "title": "X", "date": "2026-07-12"}]}'
    parsed = parse_ai_response(raw)
    assert len(parsed.actions) == 1
    assert parsed.actions[0]["type"] == "add_task"


def test_markdown_fenced_json():
    raw = '```json\n{"reply": "Ок", "actions": []}\n```'
    parsed = parse_ai_response(raw)
    assert parsed.reply == "Ок"


def test_json_with_preamble():
    raw = 'Вот мой ответ:\n{"reply": "Ок", "actions": []}\nНадеюсь, помог!'
    parsed = parse_ai_response(raw)
    assert parsed.reply == "Ок"


def test_broken_json_falls_back_to_reply():
    raw = '{"reply": "незакрытая скобка", "actions": ['
    parsed = parse_ai_response(raw)
    assert parsed.reply == raw
    assert parsed.actions == []


def test_missing_reply_falls_back():
    raw = '{"actions": []}'
    parsed = parse_ai_response(raw)
    assert parsed.reply == raw


def test_non_dict_actions_dropped():
    raw = '{"reply": "Ок", "actions": ["строка", 42, {"type": "add_goal", "title": "Цель"}]}'
    parsed = parse_ai_response(raw)
    assert len(parsed.actions) == 1


def test_morning_response():
    raw = '{"tasks": [{"title": "Задача 1", "description": null, "goal_id": null}]}'
    tasks = parse_morning_response(raw)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Задача 1"


def test_morning_response_garbage():
    assert parse_morning_response("не json вообще") == []


# ── validate_action (с временной БД) ─────────────────────────────

@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    schema = (Path(__file__).parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")
    conn.execute("INSERT INTO goals (user_id, title) VALUES (1, 'Цель')")
    conn.execute(
        "INSERT INTO tasks (user_id, title, date) VALUES (1, 'Задача', '2026-07-11')"
    )
    # чужие пользователь и задача — для проверки принадлежности
    conn.execute("INSERT INTO users (telegram_id) VALUES (222)")
    conn.execute(
        "INSERT INTO tasks (user_id, title, date) VALUES (2, 'Чужая', '2026-07-11')"
    )
    conn.commit()
    conn.close()

    def _test_connect(_ignored=None):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON;")
        return c

    monkeypatch.setattr(repo, "_connect", _test_connect)
    return db_path


def test_add_goal_valid(temp_db):
    action = {"type": "add_goal", "title": "Новая цель", "priority": 3}
    result = actions_service.validate_action(action, user_id=1)
    assert result == {
        "type": "add_goal",
        "title": "Новая цель",
        "description": None,
        "priority": 3,
        "target_date": None,
    }


def test_add_goal_no_title(temp_db):
    assert actions_service.validate_action({"type": "add_goal"}, 1) is None


def test_add_goal_bad_priority_normalized(temp_db):
    result = actions_service.validate_action(
        {"type": "add_goal", "title": "X", "priority": 99}, 1
    )
    assert result["priority"] == 0


def test_add_task_valid(temp_db):
    action = {"type": "add_task", "title": "Т", "date": "2026-07-12", "goal_id": 1}
    result = actions_service.validate_action(action, 1)
    assert result["goal_id"] == 1


def test_add_task_bad_date(temp_db):
    action = {"type": "add_task", "title": "Т", "date": "завтра"}
    assert actions_service.validate_action(action, 1) is None


def test_add_task_foreign_goal_nullified(temp_db):
    action = {"type": "add_task", "title": "Т", "date": "2026-07-12", "goal_id": 999}
    result = actions_service.validate_action(action, 1)
    assert result["goal_id"] is None


def test_complete_task_valid(temp_db):
    result = actions_service.validate_action({"type": "complete_task", "task_id": 1}, 1)
    assert result == {"type": "complete_task", "task_id": 1}


def test_complete_foreign_task_rejected(temp_db):
    # задача id=2 принадлежит пользователю 2
    assert actions_service.validate_action({"type": "complete_task", "task_id": 2}, 1) is None


def test_reschedule_valid(temp_db):
    result = actions_service.validate_action(
        {"type": "reschedule", "task_id": 1, "new_date": "2026-07-15"}, 1
    )
    assert result["new_date"] == "2026-07-15"


def test_unknown_type_rejected(temp_db):
    assert actions_service.validate_action({"type": "drop_database"}, 1) is None


def test_max_actions_cap(temp_db):
    actions = [
        {"type": "add_goal", "title": f"Цель {i}"} for i in range(10)
    ]
    valid = actions_service.validate_actions(actions, 1)
    assert len(valid) == 5
