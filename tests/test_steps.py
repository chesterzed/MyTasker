"""
Тесты планов целей (goal_steps): валидация/применение set_plan и update_step,
логика тумблеров и прогресса в репозитории.
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.services import actions as actions_service
from bot.services import repository as repo
from bot.services.ai_orchestrator import parse_plan_response
from db.migrate import apply_migrations


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")           # id=1
    conn.execute("INSERT INTO goals (user_id, title) VALUES (1, 'Японский')")  # id=1
    conn.execute(
        "INSERT INTO goal_steps (user_id, goal_id, order_index, title) "
        "VALUES (1, 1, 0, 'Установить Duolingo')"                          # id=1
    )
    conn.execute(
        "INSERT INTO goal_steps (user_id, goal_id, order_index, title, progress_total) "
        "VALUES (1, 1, 1, 'Пройти 3 урока', 3)"                            # id=2
    )
    # чужой пользователь со своим шагом — для проверки принадлежности
    conn.execute("INSERT INTO users (telegram_id) VALUES (222)")           # id=2
    conn.execute("INSERT INTO goals (user_id, title) VALUES (2, 'Чужая')")  # id=2
    conn.execute(
        "INSERT INTO goal_steps (user_id, goal_id, order_index, title) "
        "VALUES (2, 2, 0, 'Чужой шаг')"                                    # id=3
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


# ── parse_plan_response ──────────────────────────────────────────

def test_parse_plan_response_ok():
    raw = '{"steps": [{"title": "Шаг 1", "progress_total": null}, {"title": "Шаг 2", "progress_total": 5}]}'
    assert len(parse_plan_response(raw)) == 2


def test_parse_plan_response_garbage():
    assert parse_plan_response("не json") == []


# ── validate: set_plan ───────────────────────────────────────────

def test_set_plan_valid(temp_db):
    action = {
        "type": "set_plan",
        "goal_id": 1,
        "steps": [{"title": "А"}, {"title": "Б", "progress_total": 3}],
    }
    result = actions_service.validate_action(action, user_id=1)
    assert result["steps"] == [
        {"title": "А", "progress_total": None},
        {"title": "Б", "progress_total": 3},
    ]


def test_set_plan_foreign_goal_rejected(temp_db):
    action = {"type": "set_plan", "goal_id": 2, "steps": [{"title": "X"}]}
    assert actions_service.validate_action(action, user_id=1) is None


def test_set_plan_empty_steps_rejected(temp_db):
    action = {"type": "set_plan", "goal_id": 1, "steps": []}
    assert actions_service.validate_action(action, user_id=1) is None


def test_set_plan_bad_total_normalized(temp_db):
    action = {"type": "set_plan", "goal_id": 1, "steps": [{"title": "X", "progress_total": -5}]}
    result = actions_service.validate_action(action, user_id=1)
    assert result["steps"][0]["progress_total"] is None


# ── validate: update_step ────────────────────────────────────────

def test_update_step_done(temp_db):
    result = actions_service.validate_action(
        {"type": "update_step", "step_id": 1, "done": True}, user_id=1
    )
    assert result == {"type": "update_step", "step_id": 1, "done": True}


def test_update_step_progress(temp_db):
    result = actions_service.validate_action(
        {"type": "update_step", "step_id": 2, "progress": 2}, user_id=1
    )
    assert result["progress"] == 2


def test_update_step_foreign_rejected(temp_db):
    assert actions_service.validate_action(
        {"type": "update_step", "step_id": 3, "done": True}, user_id=1
    ) is None


def test_update_step_no_fields_rejected(temp_db):
    assert actions_service.validate_action(
        {"type": "update_step", "step_id": 1}, user_id=1
    ) is None


# ── apply ────────────────────────────────────────────────────────

def test_apply_set_plan_replaces(temp_db):
    actions_service.apply_all(1, [{
        "type": "set_plan",
        "goal_id": 1,
        "steps": [{"title": "Новый шаг", "progress_total": None}],
    }])
    steps = repo.list_goal_steps(1)
    assert len(steps) == 1
    assert steps[0]["title"] == "Новый шаг"


def test_apply_update_step_progress_autodone(temp_db):
    # прогресс 2/3 — ещё pending
    actions_service.apply_all(1, [{"type": "update_step", "step_id": 2, "progress": 2}])
    step = repo.get_step(2)
    assert step["progress_current"] == 2 and step["status"] == "pending"
    # прогресс 3/3 — автоматически done
    actions_service.apply_all(1, [{"type": "update_step", "step_id": 2, "progress": 3}])
    step = repo.get_step(2)
    assert step["status"] == "done"


def test_apply_update_step_done_fills_progress(temp_db):
    actions_service.apply_all(1, [{"type": "update_step", "step_id": 2, "done": True}])
    step = repo.get_step(2)
    assert step["status"] == "done" and step["progress_current"] == 3


# ── repo toggles ─────────────────────────────────────────────────

def test_toggle_pending_done_pending(temp_db):
    repo.set_step_status(1, "done")
    assert repo.get_step(1)["status"] == "done"
    repo.set_step_status(1, "pending")
    assert repo.get_step(1)["status"] == "pending"


def test_progress_clamped_to_total(temp_db):
    repo.set_step_progress(2, 99)
    step = repo.get_step(2)
    assert step["progress_current"] == 3 and step["status"] == "done"


def test_current_goal_step_skips_done(temp_db):
    assert repo.current_goal_step(1)["id"] == 1
    repo.set_step_status(1, "done")
    assert repo.current_goal_step(1)["id"] == 2
    repo.set_step_status(2, "done")
    assert repo.current_goal_step(1) is None
