"""Uvloop setup implementation."""

from __future__ import annotations

import asyncio


def uvloop_setup() -> None:
    """Install uvloop policy if uvloop is available.

    Raises:
        ImportError: If ``uvloop`` cannot be imported.
    """

    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
