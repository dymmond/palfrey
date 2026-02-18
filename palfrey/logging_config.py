"""Logging setup utilities for Palfrey."""

from __future__ import annotations

import json
import logging
import logging.config
from configparser import RawConfigParser
from pathlib import Path
from typing import IO, Any, cast

from palfrey.config import PalfreyConfig

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def _to_logging_level(level: str | int | None) -> int:
    """Map configured log level names to Python logging level integers."""

    if level is None:
        return logging.INFO

    if isinstance(level, int):
        return level

    if level == "trace":
        return TRACE_LEVEL

    mapping: dict[str, int] = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }
    return mapping.get(level, logging.INFO)


def configure_logging(config: PalfreyConfig) -> None:
    """Configure logger hierarchy from explicit config or defaults.

    Args:
        config: Runtime configuration.
    """

    log_config = config.log_config
    if log_config:
        if isinstance(log_config, dict):
            logging.config.dictConfig(cast(dict[str, Any], log_config))
            return
        if isinstance(log_config, RawConfigParser):
            logging.config.fileConfig(log_config, disable_existing_loggers=False)
            return
        if hasattr(log_config, "read"):
            logging.config.fileConfig(cast(IO[str], log_config), disable_existing_loggers=False)
            return

        path = Path(log_config)
        if path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as file:
                payload: dict[str, Any] = json.load(file)
            logging.config.dictConfig(payload)
            return
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - optional dependency branch.
                raise RuntimeError(
                    "YAML log config requires PyYAML. Install optional dependencies."
                ) from exc

            with path.open("r", encoding="utf-8") as file:
                payload = yaml.safe_load(file)
            if not isinstance(payload, dict):
                raise ValueError("YAML log config must deserialize to a dictionary.")
            logging.config.dictConfig(payload)
            return

        logging.config.fileConfig(path, disable_existing_loggers=False)
        return

    logging.basicConfig(
        level=_to_logging_level(config.log_level),
        format="%(levelname)s [%(name)s] %(message)s",
        force=True,
    )

    if config.log_level is not None:
        level = _to_logging_level(config.log_level)
        logging.getLogger("palfrey").setLevel(level)
        logging.getLogger("palfrey.error").setLevel(level)
        logging.getLogger("palfrey.access").setLevel(level)
        logging.getLogger("palfrey.asgi").setLevel(level)

    if config.access_log is False:
        access_logger = logging.getLogger("palfrey.access")
        access_logger.handlers = []
        access_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a named logger used by Palfrey internals."""

    return logging.getLogger(name)
