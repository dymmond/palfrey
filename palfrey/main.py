"""Runtime-facing API mirroring Uvicorn's ``main`` module surface."""

from __future__ import annotations

import warnings
from typing import Any

from palfrey.cli import main
from palfrey.config import Config
from palfrey.runtime import STARTUP_FAILURE, run
from palfrey.server import Server

__all__ = ["STARTUP_FAILURE", "main", "run", "Config", "Server", "__getattr__"]


def __getattr__(name: str) -> Any:
    """Provide late imports for deprecated aliases.

    Args:
        name: Attribute name requested by importers.

    Returns:
        Requested attribute.

    Raises:
        AttributeError: If the name is unsupported.
    """

    if name == "ServerState":
        warnings.warn(
            "palfrey.main.ServerState is deprecated, use palfrey.server.ServerState instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from palfrey.server import ServerState

        return ServerState
    raise AttributeError(f"module {__name__} has no attribute {name}")
