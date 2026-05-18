"""No-op event loop setup strategy for externally-managed event loops.

This module provides none_loop_setup() which performs no configuration, preserving
any event loop policy set by parent processes or third-party frameworks.
"""

from __future__ import annotations


def none_loop_setup() -> None:
    """
    Execute a no-op event loop configuration.

    This function is used when the server is explicitly configured to not manage
    the event loop policy. It is particularly useful in environments where
    the event loop has already been established by a parent process, a third-party
    library (such as a custom orchestration framework), or when running
    within a REPL where the loop is already active.

    By calling this function, the Palfrey runtime maintains its internal
    consistency by following the setup lifecycle without actually modifying
    the global 'asyncio' state.

    Returns:
        None: This function performs no operations and returns nothing.
    """

    # We do nothing here to preserve the existing global loop policy.
    return None
