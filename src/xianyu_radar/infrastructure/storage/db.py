"""SQLite connection and schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from xianyu_radar import config as cfg
from xianyu_radar.config import SCHEMA_VERSION, ensure_data_dirs

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def connect(db_path: Path | None = None, *, check_same_thread: bool = True) -> sqlite3.Connection:
    ensure_data_dirs()
    path = Path(db_path) if db_path else cfg.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
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


def init_db(db_path: Path | None = None, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Create the v1 schema and apply later migrations once, in order."""
    conn = connect(db_path, check_same_thread=check_same_thread)
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(sql)
    current = get_schema_version(conn)
    if current == 0:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            ("1",),
        )
        conn.commit()
        current = 1
    if current > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(f"Database schema {current} is newer than supported {SCHEMA_VERSION}")
    for version in range(current + 1, SCHEMA_VERSION + 1):
        files = sorted(MIGRATIONS_DIR.glob(f"{version:04d}_*.sql"))
        if len(files) != 1:
            conn.close()
            raise RuntimeError(f"Expected one migration for schema version {version}")
        migration = files[0].read_text(encoding="utf-8")
        # Early v4 databases omitted this column; current v4 installs already have it.
        if version == 9 and any(row["name"] == "unparsed_count" for row in conn.execute("PRAGMA table_info(discovery_runs)")):
            migration = ""
        try:
            conn.executescript(
                "BEGIN IMMEDIATE;\n"
                + migration
                + f"\nUPDATE meta SET value='{version}' WHERE key='schema_version';\nCOMMIT;"
            )
        except Exception:
            conn.rollback()
            conn.close()
            raise
    return conn


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}
