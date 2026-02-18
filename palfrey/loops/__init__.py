"""Event loop setup strategies used by Palfrey runtime.

This module also supports custom loop setup callables provided as import
strings in ``module:function`` format, mirroring Uvicorn's extension point.
"""

from __future__ import annotations

import importlib
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


def resolve_loop_setup(loop_mode: str) -> LoopSetup:
    """Resolve configured loop mode to a setup callable.

    Args:
        loop_mode: Loop mode value from runtime config.

    Returns:
        A no-argument setup callable.

    Raises:
        ValueError: If the loop mode cannot be resolved.
    """

    if loop_mode in LOOP_SETUPS:
        return LOOP_SETUPS[loop_mode]

    module_name, separator, attribute = loop_mode.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"Unsupported loop mode: {loop_mode}")

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ValueError(f"Unsupported loop mode: {loop_mode}") from exc

    setup = getattr(module, attribute, None)
    if not callable(setup):
        raise ValueError(f"Unsupported loop mode: {loop_mode}")
    return setup


__all__ = ["LOOP_SETUPS", "LoopSetup", "resolve_loop_setup"]
