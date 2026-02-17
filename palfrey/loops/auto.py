"""Automatic loop setup implementation."""

from __future__ import annotations

from palfrey.loops.uvloop import uvloop_setup


def auto_loop_setup() -> None:
    """Install uvloop when available, otherwise keep asyncio defaults."""

    try:
        uvloop_setup()
    except ImportError:
        return None
