"""
Тесты парсинга ответов модели и валидации действий.
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.services import actions as actions_service
from bot.services import queries as queries_service
from bot.services import repository as repo
from bot.services.ai_orchestrator import (
    assistant_turn_json,
    build_history,
    parse_ai_response,
    parse_morning_response,
)
from db.migrate import apply_migrations


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


# ── assistant_turn_json: история должна быть в JSON-контракте ─────

def test_assistant_turn_json_roundtrip():
    actions = [{"type": "add_task", "title": "Загрузить документы", "date": "2026-07-13"}]
    stored = assistant_turn_json("Добавил задачу на завтра.", actions)
    # то, что уходит в messages_log, само разбирается обратно в тот же контракт
    parsed = parse_ai_response(stored)
    assert parsed.reply == "Добавил задачу на завтра."
    assert parsed.actions == actions
    # никакой прозаической метки, которую модель могла бы спарротить
    assert "[предложены действия" not in stored


def test_assistant_turn_json_empty_actions():
    stored = assistant_turn_json("Обычный ответ.", [])
    parsed = parse_ai_response(stored)
    assert parsed.reply == "Обычный ответ."
    assert parsed.actions == []


# ── пустой reply + actions: сырой JSON не должен утекать в чат ────

def test_empty_reply_keeps_actions():
    raw = '{"reply": "", "actions": [{"type": "add_task", "title": "Занести документы", "date": "2026-07-13"}]}'
    parsed = parse_ai_response(raw)
    # действие сохранено, а сырой JSON НЕ попал в reply (иначе — баг со скриншота)
    assert parsed.reply == ""
    assert parsed.actions == [
        {"type": "add_task", "title": "Занести документы", "date": "2026-07-13"}
    ]


def test_whitespace_reply_keeps_actions():
    raw = '{"reply": "   ", "actions": [{"type": "complete_task", "task_id": 5}]}'
    parsed = parse_ai_response(raw)
    assert parsed.reply == ""
    assert parsed.actions == [{"type": "complete_task", "task_id": 5}]


def test_empty_reply_no_actions_falls_back_to_raw():
    raw = '{"reply": "", "actions": []}'
    parsed = parse_ai_response(raw)
    # пустое сообщение в Telegram отправлять нельзя — фолбэк на сырой текст
    assert parsed.reply == raw
    assert parsed.actions == []


# ── смешанный ответ «текст + JSON» ───────────────────────────────

def test_prose_prefix_before_json():
    parsed = parse_ai_response('Хорошо! {"reply": "ок", "actions": []}')
    assert parsed.reply == "ок"
    assert parsed.actions == []


def test_prose_suffix_after_json():
    parsed = parse_ai_response('{"reply": "ок", "actions": []} Готово')
    assert parsed.reply == "ок"


def test_decoy_brace_in_prose_before_json():
    # скобка-обманка в прозе не должна ломать извлечение настоящего JSON
    parsed = parse_ai_response('Вот {заметка}: {"reply": "ок", "actions": []}')
    assert parsed.reply == "ок"


def test_plain_prose_no_json_stays_reply():
    parsed = parse_ai_response("Просто текст без всякого JSON")
    assert parsed.reply == "Просто текст без всякого JSON"
    assert parsed.actions == []


# ── render_proposal_text: статус + отсутствие сырых типов ────────

def test_render_proposal_text_marks_done_and_hides_types():
    payload = {
        "reply": "Готово",
        "actions": [
            {"type": "add_goal", "title": "Цель А"},
            {"type": "add_task", "title": "Задача Б", "date": "2026-07-13"},
        ],
        "done": [True, False],
    }
    text = actions_service.render_proposal_text(payload)
    assert "add_goal" not in text and "add_task" not in text
    assert "✅ 1." in text          # применённое отмечено
    assert "2. " in text and "✅ 2." not in text  # второе ещё не применено
    assert "Готово" in text


# ── build_history: старый маркер [предложены действия] вырезается ─

def test_build_history_strips_action_marker(temp_db):
    repo.log_message(1, "user", "привет")
    repo.log_message(1, "assistant", "Ок.\n[предложены действия: add_goal]")
    history = build_history(1)
    assert history[-1].content == "Ок."
    assert "предложены действия" not in history[-1].content


# ── read-запросы (queries) ───────────────────────────────────────

def test_parse_extracts_queries():
    raw = '{"reply": "Вот задачи", "actions": [], "queries": [{"name": "list_tasks", "date": "2026-07-13"}]}'
    parsed = parse_ai_response(raw)
    assert parsed.reply == "Вот задачи"
    assert parsed.queries == [{"name": "list_tasks", "date": "2026-07-13"}]


def test_parse_empty_reply_with_queries_kept():
    raw = '{"reply": "", "actions": [], "queries": [{"name": "list_goals"}]}'
    parsed = parse_ai_response(raw)
    # пустой reply + queries НЕ должен ронять парсер в сырой дамп
    assert parsed.reply == ""
    assert parsed.queries == [{"name": "list_goals"}]


def test_validate_queries_valid_date():
    q = queries_service.validate_queries(
        [{"name": "list_tasks", "date": "2026-07-13"}], {"timezone": "UTC"}
    )
    assert q == [{"name": "list_tasks", "date": "2026-07-13"}]


def test_validate_queries_missing_or_bad_date_defaults_to_today():
    from bot.utils import today_local

    user = {"timezone": "UTC"}
    today = today_local(user)
    assert queries_service.validate_queries([{"name": "list_tasks"}], user) == [
        {"name": "list_tasks", "date": today}
    ]
    assert queries_service.validate_queries(
        [{"name": "list_tasks", "date": "завтра"}], user
    ) == [{"name": "list_tasks", "date": today}]


def test_validate_queries_list_goals_and_unknown_dropped():
    got = queries_service.validate_queries(
        [{"name": "drop_table"}, {"name": "list_goals"}], {"timezone": "UTC"}
    )
    assert got == [{"name": "list_goals"}]


def test_validate_queries_list_all_tasks():
    got = queries_service.validate_queries([{"name": "list_all_tasks"}], {"timezone": "UTC"})
    assert got == [{"name": "list_all_tasks"}]


def test_list_all_tasks_repo_orders_across_dates(temp_db):
    repo.add_task(1, title="Поздняя", date="2026-08-01")
    repo.add_task(1, title="Ранняя", date="2026-06-01")
    rows = repo.list_all_tasks(1)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)                 # по возрастанию даты
    titles = {r["title"] for r in rows}
    assert {"Поздняя", "Ранняя"} <= titles        # обе даты попали в выборку


def test_render_all_tasks_groups_by_date(temp_db):
    from bot.handlers.tasks import render_all_tasks

    repo.add_task(1, title="A", date="2026-06-01")
    repo.add_task(1, title="B", date="2026-06-02")
    text = render_all_tasks(repo.list_all_tasks(1), "<b>Все задачи:</b>")
    assert "2026-06-01" in text and "2026-06-02" in text  # даты-подзаголовки
    assert "⬜" in text                                    # иконка статуса
    assert "add_task" not in text


def test_validate_queries_cap():
    qs = [{"name": "list_goals"}] * 10
    got = queries_service.validate_queries(qs, {"timezone": "UTC"})
    assert len(got) == queries_service.MAX_QUERIES


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
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)  # тот же раннер, что и в боевом коде
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


# ── update_goal / update_task / delete_task ──────────────────────

def test_update_goal_valid(temp_db):
    action = {"type": "update_goal", "goal_id": 1, "priority": 5, "status": "paused"}
    result = actions_service.validate_action(action, 1)
    assert result["type"] == "update_goal"
    assert result["goal_id"] == 1
    assert result["fields"] == {"priority": 5, "status": "paused"}


def test_update_goal_archive(temp_db):
    result = actions_service.validate_action(
        {"type": "update_goal", "goal_id": 1, "status": "archived"}, 1
    )
    assert result["fields"] == {"status": "archived"}


def test_update_goal_no_fields_rejected(temp_db):
    assert actions_service.validate_action({"type": "update_goal", "goal_id": 1}, 1) is None


def test_update_goal_bad_status_dropped(temp_db):
    # неизвестный статус выбрасывается; раз других полей нет — действие невалидно
    assert (
        actions_service.validate_action(
            {"type": "update_goal", "goal_id": 1, "status": "deleted"}, 1
        )
        is None
    )


def test_update_goal_foreign_rejected(temp_db):
    # цель id=1 принадлежит пользователю 1; пользователь 2 её не тронет
    assert (
        actions_service.validate_action(
            {"type": "update_goal", "goal_id": 1, "priority": 3}, 2
        )
        is None
    )


def test_update_task_valid(temp_db):
    action = {"type": "update_task", "task_id": 1, "title": "Новое имя", "estimate_minutes": 45}
    result = actions_service.validate_action(action, 1)
    assert result["fields"] == {"title": "Новое имя", "estimate_minutes": 45}


def test_update_task_bad_estimate_dropped(temp_db):
    assert (
        actions_service.validate_action(
            {"type": "update_task", "task_id": 1, "estimate_minutes": -5}, 1
        )
        is None
    )


def test_update_task_foreign_rejected(temp_db):
    # задача id=2 принадлежит пользователю 2
    assert (
        actions_service.validate_action(
            {"type": "update_task", "task_id": 2, "title": "X"}, 1
        )
        is None
    )


def test_delete_task_valid(temp_db):
    result = actions_service.validate_action({"type": "delete_task", "task_id": 1}, 1)
    assert result == {"type": "delete_task", "task_id": 1}


def test_delete_foreign_task_rejected(temp_db):
    assert actions_service.validate_action({"type": "delete_task", "task_id": 2}, 1) is None


# ── delete_goal ──────────────────────────────────────────────────

def test_delete_goal_valid(temp_db):
    result = actions_service.validate_action({"type": "delete_goal", "goal_id": 1}, 1)
    assert result == {"type": "delete_goal", "goal_id": 1}


def test_delete_goal_foreign_rejected(temp_db):
    # цель id=1 принадлежит пользователю 1 — пользователь 2 её не удалит
    assert actions_service.validate_action({"type": "delete_goal", "goal_id": 1}, 2) is None


def test_delete_goal_missing_id_rejected(temp_db):
    assert actions_service.validate_action({"type": "delete_goal"}, 1) is None
    assert actions_service.validate_action({"type": "delete_goal", "goal_id": "1"}, 1) is None


def test_apply_delete_goal_removes_it(temp_db):
    actions_service.apply_all(1, [{"type": "delete_goal", "goal_id": 1}])
    assert repo.get_goal_by_id(1) is None


def test_delete_goal_orphans_linked_task_not_removes(temp_db):
    # задача, привязанная к цели, переживает удаление цели (goal_id → NULL)
    task_id = repo.add_task(1, title="Связанная", date="2026-07-12", goal_id=1)
    actions_service.apply_all(1, [{"type": "delete_goal", "goal_id": 1}])
    task = repo.get_task(task_id)
    assert task is not None and task["goal_id"] is None


# ── apply_all с новыми типами (реальная запись в temp_db) ─────────

def test_apply_update_and_delete(temp_db):
    actions = [
        {"type": "update_goal", "goal_id": 1, "fields": {"priority": 7, "status": "paused"}},
        {"type": "update_task", "task_id": 1, "fields": {"title": "Переименована"}},
    ]
    results = actions_service.apply_all(1, actions)
    assert len(results) == 2

    goal = repo.get_goal_by_id(1)
    assert goal["priority"] == 7 and goal["status"] == "paused"
    task = repo.get_task(1)
    assert task["title"] == "Переименована"

    actions_service.apply_all(1, [{"type": "delete_task", "task_id": 1}])
    assert repo.get_task(1) is None
