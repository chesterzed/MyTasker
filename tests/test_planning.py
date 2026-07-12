"""
Тесты планирования задачи из новой цели (bot/services/planning.py).
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.config import DAILY_CAPACITY_MINUTES
from bot.services import planning
from bot.services import repository as repo
from bot.services.ai_orchestrator import parse_morning_response
from db.migrate import apply_migrations


# ── has_time_left_today ──────────────────────────────────────────

def test_time_left_before_cutoff():
    # cutoff 24 → любой час < 24 → всегда есть время
    db_user = {"timezone": "UTC", "planning_cutoff_hour": 24}
    assert planning.has_time_left_today(db_user) is True


def test_no_time_left_at_cutoff_zero():
    # cutoff 0 → ни один час не меньше 0 → времени нет
    db_user = {"timezone": "UTC", "planning_cutoff_hour": 0}
    assert planning.has_time_left_today(db_user) is False


# ── remaining_budget_minutes (с временной БД) ────────────────────

@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")
    # две активные задачи с оценкой + одна выполненная (не должна списывать бюджет)
    conn.execute(
        "INSERT INTO tasks (user_id, title, date, estimate_minutes) "
        "VALUES (1, 'A', '2026-07-12', 90)"
    )
    conn.execute(
        "INSERT INTO tasks (user_id, title, date, estimate_minutes) "
        "VALUES (1, 'B', '2026-07-12', 60)"
    )
    conn.execute(
        "INSERT INTO tasks (user_id, title, date, status, estimate_minutes) "
        "VALUES (1, 'C', '2026-07-12', 'done', 120)"
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


def test_remaining_budget_subtracts_active_estimates(temp_db):
    # 480 - (90 + 60) = 330; выполненная задача C (120) не учитывается
    assert planning.remaining_budget_minutes(1, "2026-07-12") == DAILY_CAPACITY_MINUTES - 150


def test_remaining_budget_full_when_no_tasks(temp_db):
    assert planning.remaining_budget_minutes(1, "2026-01-01") == DAILY_CAPACITY_MINUTES


# ── parse ответа под задачу-из-цели (та же схема, что утром) ──────

def test_goal_task_response_parsed_with_estimate():
    raw = '{"tasks": [{"title": "Шаг 1", "description": null, "estimate_minutes": 45, "goal_id": 3}]}'
    tasks = parse_morning_response(raw)
    assert len(tasks) == 1
    assert tasks[0]["estimate_minutes"] == 45
    assert tasks[0]["goal_id"] == 3


def test_goal_task_empty_when_no_time():
    assert parse_morning_response('{"tasks": []}') == []
