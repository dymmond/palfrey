from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def load_env_file(path: str | os.PathLike[str] | None) -> None:
    """
    Loads environment variables from a specified file into the current process environment.

    This function attempts to utilize the 'python-dotenv' library if available for robust
    parsing. If the library is missing, it falls back to a manual parser that processes
    standard 'KEY=VALUE' formats. Existing environment variables are prioritized and will
    not be overwritten.

    Args:
        path (str | os.PathLike[str] | None): The path to the environment file. If the path
            is None or does not exist on the filesystem, the function returns without error.
    """
    if not path:
        return

    env_path = Path(path)
    if not env_path.exists():
        return

    # Attempt to use professional dotenv parser for better escaping/quote handling
    dotenv_loader: Callable[..., bool] | None = None
    try:
        from dotenv import load_dotenv as imported_loader
    except ImportError:
        # Fallback to manual parsing if python-dotenv is not installed
        pass
    else:
        dotenv_loader = imported_loader

    if dotenv_loader is not None:
        # override=False ensures we respect existing environment settings
        dotenv_loader(dotenv_path=env_path, override=False)
        return

    # Manual parsing logic for environments without the 'python-dotenv' dependency
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        # Filter out empty lines, comments, or lines without a valid assignment
        if not line or line.startswith("#") or "=" not in line:
            continue

        # Split at the first '=' to handle values that may contain assignment characters
        key, value = line.split("=", 1)

        # Use setdefault to ensure existing process variables take precedence
        os.environ.setdefault(key.strip(), value.strip())
