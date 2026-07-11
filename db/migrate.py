"""
db/migrate.py

Лёгкий раннер миграций на встроенном PRAGMA user_version.
Миграции — пронумерованные .sql в db/migrations/ (001_*.sql, 002_*.sql, ...).
Применяются по порядку те, чей номер больше текущего user_version.
Идемпотентно: повторный запуск ничего не делает.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NUM_RE = re.compile(r"^(\d+)")


def _discover() -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _NUM_RE.match(path.name)
        if match:
            files.append((int(match.group(1)), path))
    return sorted(files)


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Накатывает недостающие миграции; возвращает список применённых версий."""
    conn.execute("PRAGMA foreign_keys = ON;")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    applied: list[int] = []
    for version, path in _discover():
        if version <= current:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        # user_version нельзя параметризовать (?-плейсхолдером), только литералом
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
        applied.append(version)
    return applied
