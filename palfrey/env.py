"""Environment loading helpers."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def load_env_file(path: str | os.PathLike[str] | None) -> None:
    """Load `KEY=VALUE` pairs from an env file.

    Args:
        path: Optional path to an environment file.
    """

    if not path:
        return

    env_path = Path(path)
    if not env_path.exists():
        return

    dotenv_loader: Callable[..., bool] | None = None
    try:
        from dotenv import load_dotenv as imported_loader
    except ImportError:
        pass
    else:
        dotenv_loader = imported_loader

    if dotenv_loader is not None:
        dotenv_loader(dotenv_path=env_path, override=False)
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
