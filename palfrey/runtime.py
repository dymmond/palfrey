"""Top-level runtime orchestration for Palfrey."""

from __future__ import annotations

import os
import sys
from typing import Any, overload

from palfrey.config import PalfreyConfig
from palfrey.env import load_env_file
from palfrey.logging_config import get_logger
from palfrey.loops import resolve_loop_setup
from palfrey.server import PalfreyServer
from palfrey.supervisors.reload import ReloadSupervisor, build_reload_argv
from palfrey.supervisors.workers import WorkerSupervisor
from palfrey.types import AppType

logger = get_logger("palfrey.runtime")
STARTUP_FAILURE = 3


def _configure_loop(loop_mode: str) -> None:
    """Apply event loop policy according to configured mode."""

    resolve_loop_setup(loop_mode)()


def _run_config(config: PalfreyConfig) -> PalfreyServer | None:
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

    if (config.reload or config.workers_count > 1) and not isinstance(config.app, str):
        raise RuntimeError(
            "You must pass the application as an import string to enable 'reload' or 'workers'."
        )

    try:
        if config.should_reload and os.environ.get("PALFREY_RELOAD_CHILD") != "1":
            supervisor = ReloadSupervisor(config=config, argv=build_reload_argv())
            supervisor.run()
            return None
        if config.workers_count > 1:
            WorkerSupervisor(config=config).run()
            return None

        server = PalfreyServer(config)
        server.run()
        return server
    finally:
        if config.uds and os.path.exists(config.uds):
            os.remove(config.uds)


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

    if config.app_dir is not None:
        sys.path.insert(0, config.app_dir)

    if (config.reload or config.workers_count > 1) and not isinstance(config.app, str):
        logger.warning(
            "You must pass the application as an import string to enable 'reload' or 'workers'."
        )
        raise SystemExit(1)

    try:
        server = _run_config(config)
    except KeyboardInterrupt:
        return

    if (
        server is not None
        and not server.started
        and not config.should_reload
        and config.workers_count == 1
    ):
        raise SystemExit(STARTUP_FAILURE)
