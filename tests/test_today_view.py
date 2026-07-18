"""
Тесты разбивки /today на «Приоритетные» / «Прошлые».
Запуск: python -m pytest tests/ -v
"""
from __future__ import annotations

from bot import texts
from bot.handlers.tasks import render_task_list


def _task(id_, title, date, planned_date, status="pending", estimate=None):
    # sqlite3.Row умеет доступ по ключу и .keys() — dict достаточно для рендера
    return {
        "id": id_,
        "title": title,
        "date": date,
        "planned_date": planned_date,
        "status": status,
        "estimate_minutes": estimate,
    }


def _button_labels(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def _button_task_ids(kb):
    # callback_data вида "task:done:<id>"
    return [btn.callback_data.split(":")[-1] for row in kb.inline_keyboard for btn in row]


def test_split_priority_and_past():
    tasks = [
        _task(1, "Сегодняшняя A", "2026-07-14", "2026-07-14"),
        _task(2, "Сегодняшняя B", "2026-07-14", "2026-07-14"),
        _task(3, "Перенесённая", "2026-07-14", "2026-07-10"),
    ]
    text, kb = render_task_list(tasks, texts.TODAY_HEADER)
    assert texts.TODAY_SECTION_PRIORITY in text
    assert texts.TODAY_SECTION_PAST in text
    # приоритетные идут раньше прошлых
    assert text.index(texts.TODAY_SECTION_PRIORITY) < text.index(texts.TODAY_SECTION_PAST)
    # сквозная нумерация: 1,2 в приоритетных, 3 в прошлых
    assert "1. Сегодняшняя A" in text
    assert "2. Сегодняшняя B" in text
    assert "3. Перенесённая" in text
    # у перенесённой — пометка изначальной даты
    assert "изначально на 10.07" in text


def test_buttons_cover_both_groups_with_matching_numbers():
    tasks = [
        _task(10, "A", "2026-07-14", "2026-07-14"),
        _task(20, "B", "2026-07-14", "2026-07-10"),  # прошлая
    ]
    _text, kb = render_task_list(tasks, texts.TODAY_HEADER)
    labels = _button_labels(kb)
    ids = _button_task_ids(kb)
    assert labels == ["✅ 1", "✅ 2"]            # номера совпадают с текстом
    assert ids == ["10", "20"]                   # 1 → приоритетная, 2 → прошлая


def test_no_past_section_when_all_priority():
    tasks = [_task(1, "A", "2026-07-14", "2026-07-14")]
    text, _kb = render_task_list(tasks, texts.TODAY_HEADER)
    assert texts.TODAY_SECTION_PRIORITY in text
    assert texts.TODAY_SECTION_PAST not in text


def test_done_task_has_no_button_but_keeps_number():
    tasks = [
        _task(1, "Готова", "2026-07-14", "2026-07-14", status="done"),
        _task(2, "Активна", "2026-07-14", "2026-07-14"),
    ]
    text, kb = render_task_list(tasks, texts.TODAY_HEADER)
    assert "✅ 1. Готова" in text        # done-иконка + номер
    assert _button_labels(kb) == ["✅ 2"]  # кнопка только на pending #2
    assert _button_task_ids(kb) == ["2"]
