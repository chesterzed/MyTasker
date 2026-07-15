PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    time       TEXT NOT NULL,             -- 'HH:MM' (24ч)
    created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

-- Существующим пользователям — прежнее поведение (08:00 план + 14:00 чек-ин)
INSERT INTO reminders (user_id, time) SELECT id, '08:00' FROM users;
INSERT INTO reminders (user_id, time) SELECT id, '14:00' FROM users;
