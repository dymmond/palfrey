from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from palfrey.cli import main
from palfrey.config import Config
from palfrey.runtime import STARTUP_FAILURE, run
from palfrey.server import Server

if TYPE_CHECKING:
    pass

__all__ = ["STARTUP_FAILURE", "main", "run", "Config", "Server", "__getattr__"]


def __getattr__(name: str) -> Any:
    """
    Dynamically handle attribute access for the module to support deprecated aliases.

    This function implements PEP 562 to allow for lazy imports and to provide a
    mechanism for issuing deprecation warnings when specific attributes are
    accessed. It ensures backward compatibility while encouraging the use of
    updated module paths.

    Args:
        name (str): The name of the attribute being requested from this module.

    Returns:
        Any: The requested attribute, such as a class or a constant, if it is
            recognized as a supported deprecated alias.

    Raises:
        AttributeError: If the requested attribute name is not recognized or
            supported by this module's dynamic lookup logic.
    """

    if name == "ServerState":
        # Notify the user that this specific path is no longer the preferred way
        # to access the ServerState class.
        warnings.warn(
            "palfrey.main.ServerState is deprecated, use palfrey.server.ServerState instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Perform a late import to avoid unnecessary overhead if the alias is never used.
        from palfrey.server import ServerState

        return ServerState

    # Standard behavior: raise an AttributeError if the name doesn't exist
    raise AttributeError(f"module {__name__} has no attribute {name}")
