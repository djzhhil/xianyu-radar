"""Move legacy flat data/ into data/demo and init empty data/prod."""

from __future__ import annotations

import shutil

from xianyu_radar.config import ROOT_DIR, apply_env, paths_for
from xianyu_radar.storage.db import init_db


def isolate_demo_data() -> dict:
    data = ROOT_DIR / "data"
    legacy_db = data / "radar.sqlite3"
    legacy_state = data / "state"

    demo = paths_for("demo")
    prod = paths_for("prod")
    for p in (
        demo["data_dir"],
        demo["state_dir"],
        demo["debug_dir"],
        prod["data_dir"],
        prod["state_dir"],
        prod["debug_dir"],
    ):
        p.mkdir(parents=True, exist_ok=True)

    moved: list[str] = []
    if legacy_db.exists():
        if not demo["db_path"].exists():
            shutil.move(str(legacy_db), str(demo["db_path"]))
            moved.append(f"db → {demo['db_path']}")
        else:
            archive = demo["data_dir"] / "radar.legacy-flat.sqlite3"
            shutil.move(str(legacy_db), str(archive))
            moved.append(f"db → {archive}")

    if legacy_state.is_dir():
        for f in legacy_state.glob("*"):
            if f.is_dir():
                continue
            dest = demo["state_dir"] / f.name
            if dest.exists():
                dest = demo["state_dir"] / f"legacy_{f.name}"
            shutil.move(str(f), str(dest))
            moved.append(f"state/{f.name} → {dest}")

    apply_env("prod")
    conn = init_db(prod["db_path"])
    prod_counts = {
        "sellers": conn.execute("SELECT COUNT(*) c FROM sellers").fetchone()[0],
        "items": conn.execute("SELECT COUNT(*) c FROM items").fetchone()[0],
        "candidates": conn.execute("SELECT COUNT(*) c FROM candidates").fetchone()[0],
    }
    conn.close()

    apply_env("demo")
    dconn = init_db(demo["db_path"])
    demo_counts = {
        "sellers": dconn.execute("SELECT COUNT(*) c FROM sellers").fetchone()[0],
        "items": dconn.execute("SELECT COUNT(*) c FROM items").fetchone()[0],
        "candidates": dconn.execute("SELECT COUNT(*) c FROM candidates").fetchone()[0],
    }
    dconn.close()

    apply_env("prod")
    return {
        "moved": moved,
        "prod": {"db": str(prod["db_path"]), "counts": prod_counts},
        "demo": {"db": str(demo["db_path"]), "counts": demo_counts},
        "active_env": "prod",
    }
