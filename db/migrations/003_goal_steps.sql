-- 003_goal_steps.sql
-- План достижения цели: пошаговые пункты. Счётные шаги («пройти 3 урока»)
-- имеют progress_total и текущий progress_current (рендерится как «(2/3)»).

CREATE TABLE IF NOT EXISTS goal_steps (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id          INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    order_index      INTEGER NOT NULL DEFAULT 0,
    title            TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total   INTEGER,            -- NULL = обычный шаг без счётчика
    created_at       TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_goal_steps_goal ON goal_steps(goal_id, order_index);
CREATE TRIGGER IF NOT EXISTS trg_goal_steps_updated_at
AFTER UPDATE ON goal_steps FOR EACH ROW
BEGIN UPDATE goal_steps SET updated_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id; END;
