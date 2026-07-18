-- 006_settings.sql
-- Пользовательские настройки (/settings), хранятся прямо в users.

-- Тумблер «Визуал»: показывать ли выполненные задачи в today-списках (1 = да).
ALTER TABLE users ADD COLUMN show_completed_today INTEGER NOT NULL DEFAULT 1
    CHECK (show_completed_today IN (0, 1));
-- Выбранная модель активного провайдера (напр. 'claude-opus-4-8' / 'qwen2.5:14b').
ALTER TABLE users ADD COLUMN ai_model TEXT;
