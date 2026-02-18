"""Event loop setup strategies used by Palfrey runtime."""

from __future__ import annotations

from collections.abc import Callable

from palfrey.loops.asyncio import asyncio_setup
from palfrey.loops.auto import auto_loop_setup
from palfrey.loops.none import none_loop_setup
from palfrey.loops.uvloop import uvloop_setup

LoopSetup = Callable[[], None]

LOOP_SETUPS: dict[str, LoopSetup] = {
    "none": none_loop_setup,
    "auto": auto_loop_setup,
    "asyncio": asyncio_setup,
    "uvloop": uvloop_setup,
}

__all__ = ["LOOP_SETUPS", "LoopSetup"]
