"""Run uvicorn for the web UI + API."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="radar-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--env", default=None, help="prod | demo (default: RADAR_ENV or prod)")
    args = parser.parse_args(argv)

    if args.env:
        os.environ["RADAR_ENV"] = args.env

    from xianyu_radar.config import apply_env

    apply_env(args.env)

    import uvicorn

    uvicorn.run(
        "xianyu_radar.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
