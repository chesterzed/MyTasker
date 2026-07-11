"""
db/init_db.py

Создаёт БД AimTracker и накатывает все миграции из db/migrations/.
Безопасно запускать многократно (миграции идемпотентны через PRAGMA user_version).

Usage:
    python db/init_db.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# позволяет запускать напрямую: `python db/init_db.py` (не только `python -m db.init_db`)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.migrate import apply_migrations

DB_PATH = PROJECT_ROOT / "data" / "aimtracker.db"


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")  # снижает "database is locked"
        applied = apply_migrations(conn)
    finally:
        conn.close()

    if applied:
        print(f"Database at {db_path}: применено миграций {applied}")
    else:
        print(f"Database at {db_path}: применено миграций 0 (уже актуальна)")
    _verify(db_path)


def _verify(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name;"
        ).fetchall()
        tables = [r[0] for r in rows]
        print(f"user_version={version}, таблиц {len(tables)}: {', '.join(tables)}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
