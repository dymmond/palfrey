from __future__ import annotations

import asyncio


def uvloop_setup() -> None:
    """
    Configure and install the uvloop event loop policy for the current process.

    uvloop is a fast, drop-in replacement for the built-in asyncio event loop,
    implemented in Cython and built on top of libuv. This function attempts to
    import the 'uvloop' package and sets its EventLoopPolicy as the global
    standard for the running application.

    Note:
        uvloop is primarily supported on POSIX systems (Linux, macOS). On
        unsupported platforms like Windows, calling this function will
        typically result in an ImportError or a platform-related error.

    Raises:
        ImportError: If the 'uvloop' package is not installed in the
            current Python environment.
    """

    # Local import to prevent hard dependency if the user only wants asyncio
    import uvloop

    # Replace the standard asyncio policy with the libuv-backed implementation
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
