"""Top-level runtime orchestration for Palfrey."""

from __future__ import annotations

import os
from typing import Any, overload

from palfrey.config import PalfreyConfig
from palfrey.env import load_env_file
from palfrey.logging_config import get_logger
from palfrey.loops import LOOP_SETUPS
from palfrey.server import PalfreyServer
from palfrey.supervisors.reload import ReloadSupervisor, build_reload_argv
from palfrey.supervisors.workers import WorkerSupervisor
from palfrey.types import AppType

logger = get_logger("palfrey.runtime")


def _configure_loop(loop_mode: str) -> None:
    """Apply event loop policy according to configured mode."""

    if loop_mode not in LOOP_SETUPS:
        raise ValueError(f"Unsupported loop mode: {loop_mode}")
    LOOP_SETUPS[loop_mode]()


def _run_config(config: PalfreyConfig) -> None:
    """Run Palfrey according to supervision and runtime configuration.

    Args:
        config: Runtime options.

    Raises:
        RuntimeError: If incompatible options are selected.
    """

    load_env_file(config.env_file)
    _configure_loop(config.loop)

    if config.reload and config.workers_count > 1:
        logger.warning('"workers" flag is ignored when reloading is enabled.')

    if config.reload and not isinstance(config.app, str):
        raise RuntimeError("Reload mode requires the application to be an import string.")

    if config.workers_count > 1 and not isinstance(config.app, str):
        raise RuntimeError("Worker mode requires the application to be an import string.")

    if config.reload and os.environ.get("PALFREY_RELOAD_CHILD") != "1":
        supervisor = ReloadSupervisor(config=config, argv=build_reload_argv())
        supervisor.run()
        return
    if config.workers_count > 1:
        WorkerSupervisor(config=config).run()
        return

    server = PalfreyServer(config)
    server.run()


@overload
def run(config: PalfreyConfig) -> None:
    """Run Palfrey from a pre-built configuration."""


@overload
def run(app: AppType, **kwargs: Any) -> None:
    """Run Palfrey from an application callable/import string and keyword options."""


def run(config_or_app: PalfreyConfig | AppType, **kwargs: Any) -> None:
    """Run Palfrey using a config object or direct app/kwargs inputs.

    Args:
        config_or_app: Either a ``PalfreyConfig`` instance or an app target.
        **kwargs: Configuration options when ``config_or_app`` is an app target.
    """
    if isinstance(config_or_app, PalfreyConfig):
        config = config_or_app
    else:
        config = PalfreyConfig(app=config_or_app, **kwargs)
    _run_config(config)
