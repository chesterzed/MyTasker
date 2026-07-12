"""
Тесты клавиатуры предложений (кнопки «✅ n», «Подтвердить все», «Отклонить», «Изменить»).
Требуют aiogram. Запуск: python -m pytest tests/test_proposals_view.py -v
"""
from __future__ import annotations

from bot.keyboards import PendingActionCb, proposal_kb

_A2 = [
    {"type": "add_goal", "title": "Цель"},
    {"type": "add_task", "title": "Задача", "date": "2026-07-13"},
]


def _labels(markup):
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _callbacks(markup):
    return {btn.text: btn.callback_data for row in markup.inline_keyboard for btn in row}


def test_single_action_no_confirm_all():
    kb = proposal_kb(5, [_A2[0]], [False])
    labels = _labels(kb)
    assert "✅ 1" in labels
    assert "✅ Подтвердить все" not in labels  # одно действие — кнопки «все» нет
    assert "❌ Отклонить" in labels and "✏️ Изменить" in labels


def test_multi_action_has_confirm_all():
    kb = proposal_kb(5, _A2, [False, False])
    labels = _labels(kb)
    assert "✅ 1" in labels and "✅ 2" in labels
    assert "✅ Подтвердить все" in labels


def test_done_action_hidden_and_confirm_all_drops_at_one_left():
    kb = proposal_kb(5, _A2, [True, False])
    labels = _labels(kb)
    assert "✅ 1" not in labels          # применённое действие скрыто
    assert "✅ 2" in labels
    assert "✅ Подтвердить все" not in labels  # осталось одно


def test_none_when_all_done():
    assert proposal_kb(5, [_A2[0]], [True]) is None


def test_apply_callback_carries_index():
    kb = proposal_kb(7, _A2, [False, False])
    cb = PendingActionCb.unpack(_callbacks(kb)["✅ 2"])
    assert cb.action == "apply" and cb.idx == 1 and cb.pa_id == 7
