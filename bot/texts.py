"""
bot/texts.py

Все русские строки интерфейса в одном месте.
"""

GREETING = (
    "Привет, {name}! 👋\n\n"
    "Я — AimTracker, твой ассистент по целям. Каждое утро я присылаю небольшие "
    "задачи, которые приближают тебя к целям, а днём спрашиваю, как успехи.\n\n"
    "Можешь просто писать мне что угодно — я пойму и предложу, что сделать.\n\n"
    "Начни с добавления цели: /addaim\n"
    "Все команды: /help"
)

HELP = (
    "<b>Команды:</b>\n"
    "/start — приветствие и регистрация\n"
    "/addaim — добавить цель\n"
    "/aims — текущие цели\n"
    "/today — задачи на сегодня\n"
    "/setkey — настроить нейросеть (API-ключ / модель)\n"
    "/provider — переключить нейросеть (Claude / Ollama)\n"
    "/timezone — установить часовой пояс\n"
    "/cutoff — до какого часа планировать день\n"
    "/notifications — времена напоминаний\n"
    "/cancel — отменить текущий диалог\n"
    "/help — это сообщение\n\n"
    "А любое обычное сообщение — это разговор с нейросетью: она ответит "
    "и при необходимости предложит добавить цели или задачи. "
    "Голосовые сообщения тоже понимаю: распознаю речь и отвечу."
)

CANCELLED = "Отменено."
NOTHING_TO_CANCEL = "Нечего отменять."
UNKNOWN_COMMAND = "Неизвестная команда. Список команд: /help"

# /addaim
ADDAIM_ASK = (
    "Какую цель хочешь добавить? Опиши её.\n"
    "Первая строка станет названием, остальное — описанием."
)
ADDAIM_SAVED = "Цель «{title}» добавлена ✅\nТеперь я буду учитывать её при планировании задач."
ADDAIM_TASKS_HEADER = "<b>Обновил задачи на сегодня:</b>"

# /aims
AIMS_HEADER = "<b>Твои цели:</b>"
AIMS_EMPTY = "У тебя пока нет целей. Добавь первую: /addaim"

# read-запросы (list_tasks по дате)
TASKS_ON_DATE_HEADER = "<b>Задачи на {date}:</b>"
TASKS_ON_DATE_EMPTY = "На {date} задач нет."
ALL_TASKS_HEADER = "<b>Все твои задачи:</b>"
ALL_TASKS_EMPTY = "У тебя пока нет задач."

# /today
TODAY_HEADER = "<b>Задачи на сегодня:</b>"
TODAY_EMPTY = (
    "Задач на сегодня нет.\n"
    "Утром я пришлю план — или просто напиши мне, что хочешь сделать."
)
# показывается под пустым /today: видно, по какой дате/поясу считалось «сегодня»
TODAY_EMPTY_TZ_NOTE = "🕓 Сегодня по твоему поясу <b>{tz}</b>: {date}. Сменить пояс: /timezone"

# /timezone
TIMEZONE_ASK = (
    "Пришли название часового пояса в формате IANA, например:\n"
    "<code>Europe/Moscow</code>, <code>Asia/Yekaterinburg</code>, <code>Europe/Berlin</code>"
)
TIMEZONE_SAVED = "Часовой пояс установлен: {tz} ✅"
TIMEZONE_INVALID = "Не похоже на часовой пояс. Пример: <code>Europe/Moscow</code>. Попробуй ещё раз или /cancel."
# нудж при онбординге, если пояс всё ещё дефолтный UTC
TIMEZONE_HINT = (
    "🕓 Твой часовой пояс сейчас — <b>UTC</b>. Если ты не в UTC, задай свой командой "
    "/timezone, иначе «сегодня» (и задачи на день) будут считаться по UTC и могут "
    "не совпадать с твоим днём."
)

# /cutoff
CUTOFF_ASK = (
    "До какого часа имеет смысл добавлять задачи на сегодня?\n"
    "Пришли число от 0 до 23 (по умолчанию 21 — то есть до 21:00).\n"
    "Позже этого часа новая цель просто сохранится, без задачи на сегодня."
)
CUTOFF_SAVED = "Готово ✅ Планирую задачи на сегодня до {hour}:00."
CUTOFF_INVALID = "Нужно целое число от 0 до 23. Попробуй ещё раз или /cancel."

# /setkey
SETKEY_CHOOSE_PROVIDER = "Какую нейросеть настроим?"
SETKEY_ASK_KEY = (
    "Пришли API-ключ для Claude.\n"
    "⚠️ Сообщение с ключом будет удалено из чата после сохранения."
)
SETKEY_ASK_OLLAMA_MODEL = (
    "Для Ollama ключ не нужен. Пришли имя локальной модели "
    "(например, <code>llama3.1</code>) — она должна быть уже скачана через <code>ollama pull</code>."
)
SETKEY_KEY_SAVED = "Ключ сохранён ✅ Активная нейросеть: Claude."
SETKEY_KEY_SAVED_DELETE_FAILED = (
    "Ключ сохранён ✅ Активная нейросеть: Claude.\n"
    "⚠️ Не удалось удалить сообщение с ключом — удали его вручную."
)
SETKEY_OLLAMA_SAVED = "Модель «{model}» сохранена ✅ Активная нейросеть: Ollama."

# /provider
PROVIDER_CHOOSE = "Какую нейросеть использовать?"
PROVIDER_SET = "Активная нейросеть: {provider} ✅"
PROVIDER_NEED_KEY = "Сначала настрой ключ Claude: /setkey"
PROVIDER_NEED_MODEL = "Сначала укажи модель Ollama: /setkey"

# AI pipeline
NO_ACCESS = (
    "Подписка не активна. Обратись к администратору бота, чтобы получить доступ."
)
NO_KEY_HINT = "Нейросеть ещё не настроена. Настрой её командой /setkey"
AI_AUTH_ERROR = "Ключ не подходит — нейросеть отклонила авторизацию. Обнови ключ: /setkey"
AI_RATE_LIMIT = "Нейросеть перегружена (лимит запросов). Попробуй чуть позже."
AI_TIMEOUT = "Нейросеть не отвечает. Попробуй ещё раз чуть позже."
AI_GENERIC_ERROR = "Не получилось обратиться к нейросети. Попробуй ещё раз."

PROPOSAL_HEADER = "<b>Предлагаемые действия:</b>"
PROPOSAL_REJECTED = "❌ Отклонено"
PROPOSAL_EDIT_ASK = "✏️ Напиши, что изменить в этом плане:"
STALE_PROPOSAL = "Это предложение уже неактуально."

BTN_CONFIRM_ALL = "✅ Подтвердить все"
BTN_REJECT = "❌ Отклонить"
BTN_EDIT = "✏️ Изменить"

ACTION_APPLIED_ANSWER = "Готово ✅"
ACTION_ALREADY_APPLIED = "Уже применено"

# Действия (рендер для пользователя)
ACTION_ADD_GOAL = "➕ Цель: «{title}»"
ACTION_ADD_TASK = "📌 Задача на {date}: «{title}»"
ACTION_COMPLETE_TASK = "✅ Отметить выполненной: «{title}»"
ACTION_RESCHEDULE = "📅 Перенести «{title}» на {date}"
ACTION_UPDATE_GOAL = "✏️ Изменить цель «{title}» ({fields})"
ACTION_DELETE_GOAL = "🗑 Удалить цель «{title}»"
ACTION_UPDATE_TASK = "✏️ Изменить задачу «{title}» ({fields})"
ACTION_DELETE_TASK = "🗑 Удалить задачу «{title}»"
ACTION_DELETE_ALL_TASKS = "🗑 Удалить все задачи ({count})"

RESULT_GOAL_ADDED = "➕ Цель «{title}» добавлена"
RESULT_TASK_ADDED = "📌 Задача «{title}» добавлена на {date}"
RESULT_TASK_COMPLETED = "✅ «{title}» отмечена выполненной"
RESULT_TASK_RESCHEDULED = "📅 «{title}» перенесена на {date}"
RESULT_GOAL_UPDATED = "✏️ Цель «{title}» обновлена"
RESULT_GOAL_DELETED = "🗑 Цель «{title}» удалена"
RESULT_TASK_UPDATED = "✏️ Задача «{title}» обновлена"
RESULT_TASK_DELETED = "🗑 Задача «{title}» удалена"
RESULT_ALL_TASKS_DELETED = "🗑 Удалено задач: {count}"

TASK_DONE_ANSWER = "Отмечено ✅"
TASK_ALREADY_DONE = "Эта задача уже отмечена."

# Голосовые сообщения
VOICE_RECOGNIZED = "🎙 Распознано:\n<i>{text}</i>"
VOICE_TOO_LONG = "Голосовое слишком длинное (максимум 5 минут). Запиши покороче или напиши текстом."
VOICE_EMPTY = "Не расслышал — в голосовом не нашлось речи. Попробуй ещё раз."
VOICE_ERROR = "Не получилось распознать голосовое. Попробуй ещё раз или напиши текстом."
VOICE_IN_DIALOG = "Сейчас я жду текстовый ответ. Напиши текстом — или /cancel, чтобы выйти из диалога."

# Scheduler / напоминания
MORNING_HEADER = "☀️ <b>Доброе утро! План на сегодня:</b>"       # первое за день
REMINDER_PROGRESS = "👋 Как успехи? Уже начал?"                    # не первое, дневное
REMINDER_DEADLINE = "⏰ Скоро дедлайн — как продвигаешься?"        # вечернее, не последнее
REMINDER_SUMMARY = "🌙 Подведём итог дня?"                         # вечернее и последнее
CHECKIN_PENDING_TASKS = "\n<b>Ещё в работе:</b>\n{tasks}"

# /notifications
NOTIF_HEADER = "<b>Твои напоминания:</b>"
NOTIF_EMPTY = "Напоминаний пока нет. Добавь первое кнопкой ➕ ниже."
NOTIF_ASK_TIME = "Во сколько напоминать? Пришли время в формате <code>ЧЧ:ММ</code>, например <code>09:30</code>."
NOTIF_INVALID_TIME = "Не похоже на время. Пример: <code>09:30</code>. Попробуй ещё раз или /cancel."
NOTIF_DUPLICATE = "Такое время уже есть в списке."
NOTIF_DELETED = "Напоминание удалено"
BTN_NOTIF_ADD = "➕ Добавить"
