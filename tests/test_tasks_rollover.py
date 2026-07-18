"""
Тесты двух дат задачи и ночного переноса.
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.services import actions as actions_service
from bot.services import repository as repo
from db.migrate import apply_migrations


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


# ── две даты при создании ────────────────────────────────────────

def test_add_task_sets_both_dates(temp_db):
    tid = repo.add_task(1, title="Завтрашняя", date="2026-07-20")
    task = repo.get_task(tid)
    assert task["date"] == "2026-07-20"
    assert task["planned_date"] == "2026-07-20"  # planned_date=None → = date


def test_add_task_explicit_planned_date(temp_db):
    tid = repo.add_task(1, title="X", date="2026-07-20", planned_date="2026-07-18")
    task = repo.get_task(tid)
    assert task["date"] == "2026-07-20" and task["planned_date"] == "2026-07-18"


# ── перенос ──────────────────────────────────────────────────────

def test_rollover_moves_overdue_pending(temp_db):
    tid = repo.add_task(1, title="Просрочена", date="2026-07-10")
    moved = repo.roll_over_tasks(1, "2026-07-14")
    assert moved == 1
    task = repo.get_task(tid)
    assert task["date"] == "2026-07-14"        # вторая дата → сегодня
    assert task["planned_date"] == "2026-07-10"  # первая неизменна


def test_rollover_ignores_done(temp_db):
    tid = repo.add_task(1, title="Сделана", date="2026-07-10")
    repo.mark_task_done(tid, "2026-07-10")
    moved = repo.roll_over_tasks(1, "2026-07-14")
    assert moved == 0
    assert repo.get_task(tid)["date"] == "2026-07-10"


def test_rollover_ignores_future(temp_db):
    tid = repo.add_task(1, title="Будущая", date="2026-07-20")
    moved = repo.roll_over_tasks(1, "2026-07-14")
    assert moved == 0
    assert repo.get_task(tid)["date"] == "2026-07-20"


def test_rollover_moves_status_moved(temp_db):
    tid = repo.add_task(1, title="Перенесённая", date="2026-07-10")
    with repo._connect() as conn:
        conn.execute("UPDATE tasks SET status = 'moved' WHERE id = ?", (tid,))
    moved = repo.roll_over_tasks(1, "2026-07-14")
    assert moved == 1


# ── дата выполнения замораживается ───────────────────────────────

def test_mark_done_freezes_second_date(temp_db):
    # задача на будущее, закрыта досрочно «сегодня»
    tid = repo.add_task(1, title="Досрочно", date="2026-07-20")
    repo.mark_task_done(tid, "2026-07-14")
    task = repo.get_task(tid)
    assert task["status"] == "done"
    assert task["date"] == "2026-07-14"          # вторая дата = день выполнения
    assert task["planned_date"] == "2026-07-20"  # первая неизменна


def test_mark_done_without_date_keeps_date(temp_db):
    tid = repo.add_task(1, title="X", date="2026-07-14")
    repo.mark_task_done(tid)  # без done_date — дата не трогается
    assert repo.get_task(tid)["date"] == "2026-07-14"


# ── apply_all прокидывает today в complete_task ──────────────────

def test_apply_complete_task_uses_today(temp_db):
    tid = repo.add_task(1, title="Через ИИ", date="2026-07-20")
    actions_service.apply_all(1, [{"type": "complete_task", "task_id": tid}], today="2026-07-14")
    task = repo.get_task(tid)
    assert task["status"] == "done" and task["date"] == "2026-07-14"
