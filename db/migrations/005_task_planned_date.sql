-- 005_task_planned_date.sql
-- «Первая» (неизменяемая) дата задачи: на какой день она изначально поставлена.
-- Существующая tasks.date остаётся «второй» (активной/подвижной) датой.

ALTER TABLE tasks ADD COLUMN planned_date TEXT;   -- NULL трактуется кодом как = date
UPDATE tasks SET planned_date = date WHERE planned_date IS NULL;
