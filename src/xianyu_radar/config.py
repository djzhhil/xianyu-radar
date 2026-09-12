"""Runtime configuration for xianyu-radar."""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: .../xianyu-radar
ROOT_DIR = Path(__file__).resolve().parents[2]

# Environments: prod (real) vs demo (fixtures / offline loop)
VALID_ENVS = ("prod", "demo")


def _normalize_env(name: str | None) -> str:
    raw = (name or os.environ.get("RADAR_ENV") or "prod").strip().lower()
    return raw if raw in VALID_ENVS else "prod"


RADAR_ENV = _normalize_env(None)

# MTOP (from zpl11 research; may change — keep configurable)
MTOP_APP_KEY = "34839810"
MTOP_BASE = "https://h5api.m.goofish.com/h5"

# Scheduler defaults (prefer stability over speed)
DEFAULT_SELLER_SCAN_INTERVAL_SEC = 90
DEFAULT_JITTER_SEC = 30
DEFAULT_DISCOVERY_INTERVAL_SEC = 3600
MAX_CONSECUTIVE_FAILURES = 5

SCHEMA_VERSION = 1


def env_root(env: str | None = None) -> Path:
    return ROOT_DIR / "data" / _normalize_env(env)


def apply_env(env: str | None = None) -> str:
    """Point DATA_DIR / DB_PATH / STATE_DIR at the selected environment."""
    global RADAR_ENV, DATA_DIR, STATE_DIR, DEBUG_DIR, DB_PATH
    RADAR_ENV = _normalize_env(env)
    DATA_DIR = env_root(RADAR_ENV)
    STATE_DIR = DATA_DIR / "state"
    DEBUG_DIR = DATA_DIR / "debug"
    DB_PATH = DATA_DIR / "radar.sqlite3"
    ensure_data_dirs()
    return RADAR_ENV


def paths_for(env: str) -> dict[str, Path]:
    root = env_root(env)
    return {
        "data_dir": root,
        "state_dir": root / "state",
        "debug_dir": root / "debug",
        "db_path": root / "radar.sqlite3",
    }


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)


# Initialize defaults (prod unless RADAR_ENV overrides)
DATA_DIR = env_root(RADAR_ENV)
STATE_DIR = DATA_DIR / "state"
DEBUG_DIR = DATA_DIR / "debug"
DB_PATH = DATA_DIR / "radar.sqlite3"
ensure_data_dirs()
