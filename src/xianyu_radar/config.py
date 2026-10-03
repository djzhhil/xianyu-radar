"""Runtime configuration for xianyu-radar."""

from __future__ import annotations

from pathlib import Path

# Repo root: .../xianyu-radar
ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT_DIR / "data"
STATE_DIR = DATA_DIR / "state"
DEBUG_DIR = DATA_DIR / "debug"
DB_PATH = DATA_DIR / "radar.sqlite3"

# MTOP (from zpl11 research; may change — keep configurable)
MTOP_APP_KEY = "34839810"
MTOP_BASE = "https://h5api.m.goofish.com/h5"

# Scheduler defaults (prefer stability over speed)
DEFAULT_SELLER_SCAN_INTERVAL_SEC = 90
DEFAULT_JITTER_SEC = 30
DEFAULT_DISCOVERY_INTERVAL_SEC = 3600
MAX_CONSECUTIVE_FAILURES = 5

SCHEMA_VERSION = 11


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
