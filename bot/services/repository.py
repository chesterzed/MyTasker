"""
bot/services/repository.py

Весь SQL бота. Синхронный sqlite3: запросы микросекундные на локальной WAL-базе,
единственный медленный путь (AI) уже асинхронный.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from db.init_db import DB_PATH


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ── users ────────────────────────────────────────────────────────

def upsert_user(telegram_id: int, username: str | None, first_name: str | None) -> sqlite3.Row:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username, "
            "first_name = excluded.first_name",
            (telegram_id, username, first_name),
        )
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_user(user_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_all_users() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM users").fetchall()


def set_role(user_id: int, role: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_timezone(user_id: int, tz: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET timezone = ? WHERE id = ?", (tz, user_id))


def set_planning_cutoff_hour(user_id: int, hour: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET planning_cutoff_hour = ? WHERE id = ?", (hour, user_id)
        )


def set_ai_provider(user_id: int, provider: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET ai_provider = ? WHERE id = ?", (provider, user_id))


def set_ollama_model(user_id: int, model: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET ollama_model = ? WHERE id = ?", (model, user_id))


# ── goals ────────────────────────────────────────────────────────

def add_goal(
    user_id: int,
    title: str,
    description: str | None = None,
    priority: int = 0,
    target_date: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO goals (user_id, title, description, priority, target_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, title, description, priority, target_date),
        )
        return cur.lastrowid


def list_active_goals(user_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM goals WHERE user_id = ? AND status = 'active' "
            "ORDER BY priority DESC, id",
            (user_id,),
        ).fetchall()


def get_goal(user_id: int, goal_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id)
        ).fetchone()


def get_goal_by_id(goal_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()


_GOAL_UPDATABLE = ("title", "description", "priority", "target_date", "status")


def update_goal(user_id: int, goal_id: int, fields: dict) -> None:
    """Частичное обновление цели: меняются только переданные (уже провалидированные)
    колонки из белого списка. Скоуп по user_id — чужую цель не тронуть."""
    cols = [k for k in fields if k in _GOAL_UPDATABLE]
    if not cols:
        return
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    values = [fields[c] for c in cols] + [goal_id, user_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE goals SET {set_clause} WHERE id = ? AND user_id = ?", values
        )


def delete_goal(user_id: int, goal_id: int) -> None:
    """Физически удаляет цель; у связанных задач goal_id → NULL (ON DELETE SET NULL)."""
    with _connect() as conn:
        conn.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))


def goal_exists(user_id: int, goal_id: int) -> bool:
    with _connect() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id)
            ).fetchone()
            is not None
        )


# ── tasks ────────────────────────────────────────────────────────

def add_task(
    user_id: int,
    title: str,
    date: str,
    description: str | None = None,
    goal_id: int | None = None,
    source: str = "user",
    order_index: int | None = None,
    estimate_minutes: int | None = None,
    planned_date: str | None = None,
) -> int:
    # planned_date — «первая» (неизменяемая) дата: на какой день поставлена.
    # При создании по умолчанию совпадает с date («второй», активной).
    planned_date = planned_date or date
    with _connect() as conn:
        if order_index is None:
            order_index = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM tasks "
                "WHERE user_id = ? AND date = ?",
                (user_id, date),
            ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO tasks "
            "(user_id, goal_id, title, description, date, planned_date, order_index, "
            "source, estimate_minutes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, goal_id, title, description, date, planned_date, order_index,
                source, estimate_minutes,
            ),
        )
        return cur.lastrowid


def list_tasks_for_date(user_id: int, date: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND date = ? ORDER BY order_index, id",
            (user_id, date),
        ).fetchall()


def list_all_tasks(user_id: int) -> list[sqlite3.Row]:
    """Все задачи пользователя (все даты и статусы), по дате и порядку."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY date, order_index, id",
            (user_id,),
        ).fetchall()


def get_task(task_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def mark_task_done(task_id: int, done_date: str | None = None) -> None:
    """Отметить выполненной. done_date (сегодня по поясу пользователя) замораживает
    «вторую» (активную) дату на дне выполнения — важно при досрочном закрытии
    задачи, назначенной на будущее."""
    with _connect() as conn:
        if done_date is None:
            conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                (_now(), task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ?, date = ? WHERE id = ?",
                (_now(), done_date, task_id),
            )


def set_task_date(task_id: int, new_date: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tasks SET date = ? WHERE id = ?", (new_date, task_id))


def roll_over_tasks(user_id: int, today: str) -> int:
    """Переносит просроченные незакрытые задачи (date < today) на сегодня.
    «Первая» дата (planned_date) не меняется. Возвращает число перенесённых."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET date = ? "
            "WHERE user_id = ? AND status IN ('pending', 'moved') AND date < ?",
            (today, user_id, today),
        )
        return cur.rowcount


_TASK_UPDATABLE = ("title", "description", "estimate_minutes")


def update_task(user_id: int, task_id: int, fields: dict) -> None:
    """Частичное обновление задачи (title/description/estimate_minutes), скоуп по user_id."""
    cols = [k for k in fields if k in _TASK_UPDATABLE]
    if not cols:
        return
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    values = [fields[c] for c in cols] + [task_id, user_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ? AND user_id = ?", values
        )


def delete_task(user_id: int, task_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )


def delete_all_tasks(user_id: int) -> int:
    """Удаляет все задачи пользователя; возвращает число удалённых."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
        return cur.rowcount


def recent_task_history(user_id: int, days: int = 7) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? "
            "AND date >= DATE('now', ?) AND date < DATE('now') "
            "ORDER BY date, order_index",
            (user_id, f"-{days} days"),
        ).fetchall()


# ── reminders ────────────────────────────────────────────────────

def list_reminders(user_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? ORDER BY time, id",
            (user_id,),
        ).fetchall()


def get_reminder(reminder_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()


def add_reminder(user_id: int, time: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (user_id, time) VALUES (?, ?)", (user_id, time)
        )
        return cur.lastrowid


# ── goal_steps (план цели) ───────────────────────────────────────

def add_goal_step(
    user_id: int,
    goal_id: int,
    title: str,
    order_index: int | None = None,
    progress_total: int | None = None,
) -> int:
    with _connect() as conn:
        if order_index is None:
            order_index = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM goal_steps WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO goal_steps (user_id, goal_id, order_index, title, progress_total) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, goal_id, order_index, title, progress_total),
        )
        return cur.lastrowid


def update_reminder(user_id: int, reminder_id: int, time: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET time = ? WHERE id = ? AND user_id = ?",
            (time, reminder_id, user_id),
        )


def delete_reminder(user_id: int, reminder_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)
        )


def ensure_default_reminders(user_id: int) -> None:
    """Если у пользователя нет напоминаний — посеять дефолтные времена."""
    from bot.config import DEFAULT_REMINDER_TIMES

    with _connect() as conn:
        has = conn.execute(
            "SELECT 1 FROM reminders WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        if has is not None:
            return
        conn.executemany(
            "INSERT INTO reminders (user_id, time) VALUES (?, ?)",
            [(user_id, t) for t in DEFAULT_REMINDER_TIMES],
        )


# ── goal_steps queries/mutations ─────────────────────────────────

def list_goal_steps(goal_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM goal_steps WHERE goal_id = ? ORDER BY order_index, id",
            (goal_id,),
        ).fetchall()


def get_step(step_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM goal_steps WHERE id = ?", (step_id,)
        ).fetchone()


def current_goal_step(goal_id: int) -> sqlite3.Row | None:
    """Первый невыполненный шаг плана (для строки «▸ …» в /aims)."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM goal_steps WHERE goal_id = ? AND status = 'pending' "
            "ORDER BY order_index, id LIMIT 1",
            (goal_id,),
        ).fetchone()


def replace_goal_steps(user_id: int, goal_id: int, steps: list[dict]) -> int:
    """Полная замена плана цели (для set_plan). steps: [{"title", "progress_total"}].
    Возвращает количество созданных шагов."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM goal_steps WHERE goal_id = ? AND user_id = ?",
            (goal_id, user_id),
        )
        for i, step in enumerate(steps):
            conn.execute(
                "INSERT INTO goal_steps (user_id, goal_id, order_index, title, progress_total) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, goal_id, i, step["title"], step.get("progress_total")),
            )
    return len(steps)


def set_step_status(step_id: int, status: str) -> None:
    """'done' — у счётного шага прогресс добивается до total; 'pending' — снять отметку."""
    with _connect() as conn:
        if status == "done":
            conn.execute(
                "UPDATE goal_steps SET status = 'done', "
                "progress_current = COALESCE(progress_total, progress_current) "
                "WHERE id = ?",
                (step_id,),
            )
        else:
            conn.execute(
                "UPDATE goal_steps SET status = 'pending' WHERE id = ?", (step_id,)
            )


def set_step_progress(step_id: int, current: int) -> None:
    """Выставить счётчик шага; при достижении total шаг автоматически done
    (и наоборот — откат ниже total снимает отметку)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE goal_steps SET "
            "progress_current = MIN(?, COALESCE(progress_total, ?)), "
            "status = CASE WHEN progress_total IS NOT NULL AND ? >= progress_total "
            "THEN 'done' ELSE 'pending' END "
            "WHERE id = ?",
            (current, current, current, step_id),
        )


# ── checkins ─────────────────────────────────────────────────────

def upsert_checkin_sent(user_id: int, date: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO checkins (user_id, date, sent_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, date) DO UPDATE SET sent_at = excluded.sent_at",
            (user_id, date, _now()),
        )


def get_open_checkin(user_id: int, date: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM checkins WHERE user_id = ? AND date = ? "
            "AND sent_at IS NOT NULL AND responded_at IS NULL",
            (user_id, date),
        ).fetchone()


def save_checkin_response(checkin_id: int, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE checkins SET user_response = ?, responded_at = ? WHERE id = ?",
            (text, _now(), checkin_id),
        )


# ── pending_actions ──────────────────────────────────────────────

def create_pending_action(user_id: int, type_: str, payload: dict) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO pending_actions (user_id, type, payload) VALUES (?, ?, ?)",
            (user_id, type_, json.dumps(payload, ensure_ascii=False)),
        )
        return cur.lastrowid


def set_pending_message_id(pa_id: int, telegram_message_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET telegram_message_id = ? WHERE id = ?",
            (telegram_message_id, pa_id),
        )


def update_pending_payload(pa_id: int, payload: dict) -> None:
    """Перезаписать JSON-payload (например, прогресс done[] при пер-экшн подтверждении)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), pa_id),
        )


def get_pending_action(pa_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM pending_actions WHERE id = ?", (pa_id,)
        ).fetchone()


def set_pending_status(pa_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET status = ? WHERE id = ?", (status, pa_id)
        )


def resolve_pending(pa_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET status = ?, resolved_at = ? WHERE id = ?",
            (status, _now(), pa_id),
        )


# ── messages_log ─────────────────────────────────────────────────

def log_message(user_id: int, role: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages_log (user_id, role, text) VALUES (?, ?, ?)",
            (user_id, role, text),
        )


def recent_messages(user_id: int, limit: int = 30) -> list[sqlite3.Row]:
    """Последние `limit` сообщений в хронологическом порядке (старые → новые)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return list(reversed(rows))
