#!/usr/bin/env python3
"""CLI wrapper around isolate_demo_data()."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xianyu_radar.storage.isolate_env import isolate_demo_data  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(isolate_demo_data(), ensure_ascii=False, indent=2))
