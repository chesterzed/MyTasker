"""
Тесты настраиваемых напоминаний: роль по позиции/времени, парсинг времени,
repo-CRUD, клавиатура меню. Часть требует aiogram (keyboards). Запуск:
python -m pytest tests/test_reminders.py -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.services import repository as repo
from bot.services.scheduler import _reminder_role
from bot.utils import parse_hhmm


# ── _reminder_role (порог вечера 18:00) ──────────────────────────

def test_role_first():
    assert _reminder_role(["09:30", "14:00", "20:00"], 0) == "first"


def test_role_progress_daytime():
    assert _reminder_role(["09:30", "14:00", "20:00"], 1) == "progress"


def test_role_deadline_evening_not_last():
    # 20:00 вечернее, но не последнее (22:00 после него)
    assert _reminder_role(["09:30", "20:00", "22:00"], 1) == "deadline"


def test_role_summary_evening_last():
    assert _reminder_role(["09:30", "14:00", "20:00"], 2) == "summary"


def test_role_single_is_first():
    assert _reminder_role(["09:30"], 0) == "first"


def test_role_last_but_not_evening_is_progress():
    # последнее, но 12:00 — не вечер → обычный дневной чек-ин
    assert _reminder_role(["09:30", "12:00"], 1) == "progress"


# ── parse_hhmm ───────────────────────────────────────────────────

def test_parse_hhmm_normalizes():
    assert parse_hhmm("9:30") == "09:30"
    assert parse_hhmm(" 09:05 ") == "09:05"
    assert parse_hhmm("23:59") == "23:59"


def test_parse_hhmm_invalid():
    for bad in ["24:00", "9:60", "abc", "09-30", "0930", "", None, 930]:
        assert parse_hhmm(bad) is None


# ── repo reminders (temp_db) ─────────────────────────────────────

@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    from db.migrate import apply_migrations

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")  # id=1
    conn.execute("INSERT INTO users (telegram_id) VALUES (222)")  # id=2
    # состояние после миграции 003 для существующих пользователей — дефолтные времена
    for uid in (1, 2):
        for t in ("08:00", "14:00"):
            conn.execute("INSERT INTO reminders (user_id, time) VALUES (?, ?)", (uid, t))
    conn.commit()
    conn.close()

    def _test_connect(_ignored=None):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON;")
        return c

    monkeypatch.setattr(repo, "_connect", _test_connect)
    yield db_path


def test_migration_003_seeds_existing_users(tmp_path: Path):
    # Проверяем реальный порядок: пользователи существуют ДО применения 003.
    from db.migrate import _discover

    db_path = tmp_path / "mig.db"
    conn = sqlite3.connect(db_path)
    for version, path in _discover():
        if version >= 3:
            break
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {version}")
    conn.execute("INSERT INTO users (telegram_id) VALUES (111)")
    conn.commit()

    # теперь накатываем недостающие (003) — оно засеет существующего пользователя
    from db.migrate import apply_migrations

    applied = apply_migrations(conn)
    assert 3 in applied
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    times = [
        r[0]
        for r in conn.execute(
            "SELECT time FROM reminders WHERE user_id = 1 ORDER BY time"
        ).fetchall()
    ]
    conn.close()
    assert times == ["08:00", "14:00"]


def test_reminders_crud_and_order(temp_db):
    rid = repo.add_reminder(1, "09:30")
    # сортировка по времени
    assert [r["time"] for r in repo.list_reminders(1)] == ["08:00", "09:30", "14:00"]
    repo.update_reminder(1, rid, "21:00")
    assert [r["time"] for r in repo.list_reminders(1)] == ["08:00", "14:00", "21:00"]
    repo.delete_reminder(1, rid)
    assert [r["time"] for r in repo.list_reminders(1)] == ["08:00", "14:00"]


def test_delete_reminder_scoped_to_user(temp_db):
    r2 = repo.list_reminders(2)[0]["id"]
    repo.delete_reminder(1, r2)  # пользователь 1 не может удалить чужое
    assert any(r["id"] == r2 for r in repo.list_reminders(2))


def test_ensure_default_reminders_idempotent(temp_db):
    before = len(repo.list_reminders(1))
    repo.ensure_default_reminders(1)  # у пользователя уже есть — ничего не добавит
    assert len(repo.list_reminders(1)) == before


def test_ensure_default_reminders_seeds_empty(temp_db):
    for r in repo.list_reminders(1):
        repo.delete_reminder(1, r["id"])
    repo.ensure_default_reminders(1)
    assert [r["time"] for r in repo.list_reminders(1)] == ["08:00", "14:00"]


# ── клавиатура меню (нужен aiogram) ──────────────────────────────

def test_notifications_kb_buttons(temp_db):
    from bot.keyboards import NotifCb, notifications_kb

    reminders = repo.list_reminders(1)  # 2 напоминания
    kb = notifications_kb(reminders)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert "❌ 1" in labels and "✏️ 1" in labels
    assert "❌ 2" in labels and "✏️ 2" in labels
    assert "➕ Добавить" in labels
    # у кнопки удаления первого — правильный reminder_id и action
    cbs = {b.text: b.callback_data for row in kb.inline_keyboard for b in row}
    cb = NotifCb.unpack(cbs["❌ 1"])
    assert cb.action == "del" and cb.reminder_id == reminders[0]["id"]
    # ➕ — action add, reminder_id по умолчанию 0
    add = NotifCb.unpack(cbs["➕ Добавить"])
    assert add.action == "add" and add.reminder_id == 0
