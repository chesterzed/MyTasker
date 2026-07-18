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


class SetCutoff(StatesGroup):
    waiting_for_hour = State()           # /cutoff → ждём час (0–23)


class EditProposal(StatesGroup):
    waiting_for_correction = State()     # нажата «Изменить»; в data: {"pa_id": int}


class Notifications(StatesGroup):
    waiting_for_new_time = State()       # ➕ → ждём HH:MM для нового напоминания
    waiting_for_edit_time = State()      # ✏️ → ждём HH:MM; в data: {"reminder_id": int}


class Settings(StatesGroup):
    waiting_for_key = State()            # /settings → Модель → claude: ждём API-ключ; data: {"model": str}
    waiting_for_tz = State()             # /settings → Часовой пояс: ждём IANA-зону
