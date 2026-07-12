-- 002_planning.sql
-- Вечерний порог планирования на пользователя (до какого часа местного времени
-- имеет смысл добавлять задачи на сегодня) и оценка длительности задачи в минутах.

ALTER TABLE users ADD COLUMN planning_cutoff_hour INTEGER NOT NULL DEFAULT 21;
ALTER TABLE tasks ADD COLUMN estimate_minutes INTEGER;
