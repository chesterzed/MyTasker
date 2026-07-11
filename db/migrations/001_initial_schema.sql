PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER NOT NULL UNIQUE,
    username            TEXT,
    first_name          TEXT,
    timezone            TEXT NOT NULL DEFAULT 'UTC',
    role                TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    -- NULL = нет активной подписки (актуально только для role='user';
    -- role='admin' в коде приложения игнорирует эту проверку)
    subscription_until  TEXT,
    ai_provider         TEXT NOT NULL DEFAULT 'ollama' CHECK (ai_provider IN ('claude', 'ollama')),
    ollama_model        TEXT DEFAULT 'qwen2.5:14b',               -- обязателен только при ai_provider='ollama'
    fsm_state           TEXT,
    fsm_context         TEXT,               -- JSON
    created_at          TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    priority     INTEGER NOT NULL DEFAULT 0,
    target_date  TEXT,
    created_at   TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at   TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_goals_user_id     ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user_status ON goals(user_id, status);
CREATE TRIGGER IF NOT EXISTS trg_goals_updated_at
AFTER UPDATE ON goals FOR EACH ROW
BEGIN UPDATE goals SET updated_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id; END;

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id      INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    date         TEXT NOT NULL,              -- YYYY-MM-DD
    order_index  INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'done', 'skipped', 'moved')),
    source       TEXT NOT NULL DEFAULT 'ai' CHECK (source IN ('ai', 'user')),
    created_at   TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_user_date ON tasks(user_id, date);
CREATE INDEX IF NOT EXISTS idx_tasks_goal_id   ON tasks(goal_id);

CREATE TABLE IF NOT EXISTS checkins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date          TEXT NOT NULL,
    sent_at       TEXT,
    user_response TEXT,
    responded_at  TEXT,
    UNIQUE (user_id, date)
);
CREATE INDEX IF NOT EXISTS idx_checkins_user_date ON checkins(user_id, date);

CREATE TABLE IF NOT EXISTS pending_actions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                 TEXT NOT NULL,      -- 'add_task' | 'add_goal' | 'reschedule' | 'bulk_add' (валидируется в Python)
    payload              TEXT NOT NULL,      -- JSON предложенных изменений
    status               TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'confirmed', 'rejected', 'editing')),
    telegram_message_id  INTEGER,
    created_at           TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions(user_id, status);

CREATE TABLE IF NOT EXISTS messages_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_log_user_created ON messages_log(user_id, created_at);

CREATE TABLE IF NOT EXISTS ai_provider_keys (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL,             -- 'claude' | 'openai' | ... (валидируется в Python)
    label         TEXT,
    encrypted_key TEXT NOT NULL,             -- Fernet-шифротекст
    is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at    TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_provider_keys_user_provider ON ai_provider_keys(user_id, provider);
-- максимум один активный ключ на пользователя+провайдера
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_provider_keys_one_active
    ON ai_provider_keys(user_id, provider) WHERE is_active = 1;
CREATE TRIGGER IF NOT EXISTS trg_ai_provider_keys_updated_at
AFTER UPDATE ON ai_provider_keys FOR EACH ROW
BEGIN UPDATE ai_provider_keys SET updated_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id; END;
