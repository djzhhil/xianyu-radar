"""Filesystem and log hygiene for secrets (cookies, broker tokens)."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

_SECRET_PATTERNS = (
    re.compile(r"(?i)(_m_h5_tk(?:_enc)?=)[^;\s\"']+"),
    re.compile(r"(?i)(cookie2=)[^;\s\"']+"),
    re.compile(r"(?i)(unb=)[^;\s\"']+"),
    re.compile(r"(?i)(sgcookie=)[^;\s\"']+"),
    re.compile(r"(?i)(havana_lgc[^=]*=)[^;\s\"']+"),
    re.compile(r"(?i)(RADAR_BROKER_TOKEN=)\S+"),
    re.compile(r"(?i)(XIANYU_BROKER_TOKEN=)\S+"),
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)\S+"),
    re.compile(r"(?i)(\"cookies\"\s*:\s*\")[^\"]+\""),
)


def redact_secrets(text: str) -> str:
    """Mask cookie / token material for logs and error strings."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(r"\1***", out)
    return out


def write_secret_file(path: Path | str, content: str, *, mode: int = 0o600) -> Path:
    """Write a secret file with restrictive permissions (owner read/write only)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, mode)
    except OSError:
        pass
    return path


def harden_path(path: Path | str, *, dir_mode: int = 0o700, file_mode: int = 0o600) -> None:
    """Apply restrictive permissions to a file or directory tree (best-effort)."""
    path = Path(path)
    if not path.exists():
        return
    try:
        if path.is_dir():
            os.chmod(path, dir_mode)
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    try:
                        os.chmod(Path(root) / d, dir_mode)
                    except OSError:
                        pass
                for name in files:
                    fp = Path(root) / name
                    try:
                        # Keep executables alone; secrets and DB get 0600
                        os.chmod(fp, file_mode)
                    except OSError:
                        pass
        else:
            os.chmod(path, file_mode)
    except OSError:
        pass


def is_world_readable(path: Path | str) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRGRP | stat.S_IROTH))
