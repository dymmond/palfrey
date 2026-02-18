"""Environment loading helpers."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | None) -> None:
    """Load `KEY=VALUE` pairs from an env file.

    Args:
        path: Optional path to an environment file.
    """

    if not path:
        return

    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
