"""SQLite connection and schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from xianyu_radar import config as cfg
from xianyu_radar.config import SCHEMA_VERSION, ensure_data_dirs

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_data_dirs()
    path = Path(db_path) if db_path else cfg.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if not row:
        return 0
    ver = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(ver["value"]) if ver else 0


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create tables if needed. Safe to call repeatedly."""
    conn = connect(db_path)
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(sql)
    current = get_schema_version(conn)
    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    return conn


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}
