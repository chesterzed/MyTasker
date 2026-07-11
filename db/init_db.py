"""
db/init_db.py

Creates the AimTracker SQLite database and applies schema.sql.
Safe to run multiple times (all DDL uses IF NOT EXISTS).

Usage:
    python db/init_db.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DB_PATH = PROJECT_ROOT / "data" / "aimtracker.db"


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    print(f"Database initialized at {db_path}")
    _verify(db_path)


def _verify(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name;"
        ).fetchall()
        tables = [r[0] for r in rows]
        print(f"Tables created ({len(tables)}): {', '.join(tables)}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
