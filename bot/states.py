"""
bot/states.py

Все FSM-состояния бота.
"""
from aiogram.fsm.state import State, StatesGroup


class AddAim(StatesGroup):
    waiting_for_goal_text = State()      # /addaim → ждём текст цели


class SetKey(StatesGroup):
    waiting_for_provider = State()       # показаны кнопки claude / ollama
    waiting_for_key = State()            # ветка claude: ждём API-ключ
    waiting_for_ollama_model = State()   # ветка ollama: ждём имя модели


class SetTimezone(StatesGroup):
    waiting_for_tz = State()             # /timezone → ждём IANA-таймзону


class EditProposal(StatesGroup):
    waiting_for_correction = State()     # нажата «Изменить»; в data: {"pa_id": int}
