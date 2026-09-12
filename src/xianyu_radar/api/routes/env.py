"""Environment switch endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from xianyu_radar import config as cfg
from xianyu_radar.config import VALID_ENVS, apply_env, paths_for
from xianyu_radar.storage.db import init_db

router = APIRouter()


class EnvBody(BaseModel):
    env: str = Field(..., description="prod | demo")


@router.get("")
def get_env() -> dict:
    return {
        "env": cfg.RADAR_ENV,
        "db_path": str(cfg.DB_PATH),
        "state_dir": str(cfg.STATE_DIR),
        "available": list(VALID_ENVS),
    }


@router.post("")
def set_env(body: EnvBody) -> dict:
    env = body.env.strip().lower()
    if env not in VALID_ENVS:
        raise HTTPException(status_code=400, detail=f"env must be one of {VALID_ENVS}")
    apply_env(env)
    init_db().close()
    return {
        "ok": True,
        "env": cfg.RADAR_ENV,
        "db_path": str(cfg.DB_PATH),
        "state_dir": str(cfg.STATE_DIR),
        "paths": {k: str(v) for k, v in paths_for(env).items()},
    }
