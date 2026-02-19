from __future__ import annotations

from palfrey.loops.uvloop import uvloop_setup


def auto_loop_setup() -> None:
    """
    Automatically select and install the most performant event loop available.

    This function attempts to initialize 'uvloop', a high-performance replacement
    for the built-in asyncio event loop based on libuv. If 'uvloop' is not
    installed or is unsupported on the current platform (such as Windows), the
    function catches the ImportError and gracefully falls back to the standard
    asyncio event loop policy.

    Returns:
        None: This function modifies the global event loop policy state.
    """

    try:
        # Attempt to install the uvloop policy for maximum I/O throughput.
        uvloop_setup()
    except ImportError:
        # Gracefully fall back to the default asyncio loop if uvloop is missing.
        return None
