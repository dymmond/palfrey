"""Logging setup utilities for Palfrey."""

from __future__ import annotations

import http
import json
import logging
import logging.config
import sys
from configparser import RawConfigParser
from copy import copy
from pathlib import Path
from typing import IO, Any, Literal, cast

import click

from palfrey.config import PalfreyConfig

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")
DEFAULT_LOG_FORMAT = "%(levelprefix)s %(message)s"
ACCESS_LOG_FORMAT = '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'


class ColourizedFormatter(logging.Formatter):
    """Formatter that supports level coloring and optional ``color_message`` fields."""

    level_name_colors = {
        TRACE_LEVEL: lambda level_name: click.style(str(level_name), fg="blue"),
        logging.DEBUG: lambda level_name: click.style(str(level_name), fg="cyan"),
        logging.INFO: lambda level_name: click.style(str(level_name), fg="green"),
        logging.WARNING: lambda level_name: click.style(str(level_name), fg="yellow"),
        logging.ERROR: lambda level_name: click.style(str(level_name), fg="red"),
        logging.CRITICAL: lambda level_name: click.style(str(level_name), fg="bright_red"),
    }

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        use_colors: bool | None = None,
    ) -> None:
        self.use_colors = sys.stdout.isatty() if use_colors is None else use_colors
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def color_level_name(self, level_name: str, level_no: int) -> str:
        """Apply level-specific terminal coloring to ``level_name``."""

        colorizer = self.level_name_colors.get(level_no)
        if colorizer is None:
            return level_name
        return colorizer(level_name)

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802
        record_copy = copy(record)
        level_name = record_copy.levelname
        separator = " " * max(0, 8 - len(record_copy.levelname))
        if self.use_colors:
            level_name = self.color_level_name(level_name, record_copy.levelno)
            if "color_message" in record_copy.__dict__:
                record_copy.msg = record_copy.__dict__["color_message"]
                record_copy.__dict__["message"] = record_copy.getMessage()
        record_copy.__dict__["levelprefix"] = f"{level_name}:{separator}"
        return super().formatMessage(record_copy)


class DefaultFormatter(ColourizedFormatter):
    """Default log formatter that targets stderr coloring behavior."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        use_colors: bool | None = None,
    ) -> None:
        resolved_colors = sys.stderr.isatty() if use_colors is None else use_colors
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, use_colors=resolved_colors)


class AccessFormatter(ColourizedFormatter):
    """Access-log formatter that annotates request line and status metadata."""

    status_code_colours = {
        1: lambda status: click.style(str(status), fg="bright_white"),
        2: lambda status: click.style(str(status), fg="green"),
        3: lambda status: click.style(str(status), fg="yellow"),
        4: lambda status: click.style(str(status), fg="red"),
        5: lambda status: click.style(str(status), fg="bright_red"),
    }

    def get_status_code(self, status_code: int) -> str:
        """Return ``'<code> <phrase>'`` with optional status colorization."""

        try:
            status_phrase = http.HTTPStatus(status_code).phrase
        except ValueError:
            status_phrase = ""
        status_text = f"{status_code} {status_phrase}".strip()
        if not self.use_colors:
            return status_text
        colorizer = self.status_code_colours.get(status_code // 100)
        if colorizer is None:
            return status_text
        return colorizer(status_text)

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802
        record_copy = copy(record)
        client_addr, method, full_path, http_version, status_code = record_copy.args  # type: ignore[misc]
        request_line = f"{method} {full_path} HTTP/{http_version}"
        if self.use_colors:
            request_line = click.style(request_line, bold=True)
        status_code_value = int(cast("int | str | bytes", status_code))
        record_copy.__dict__.update(
            {
                "client_addr": client_addr,
                "request_line": request_line,
                "status_code": self.get_status_code(status_code_value),
            }
        )
        return super().formatMessage(record_copy)


def _apply_default_formatters(config: PalfreyConfig) -> None:
    """Attach Palfrey/Uvicorn-style formatters to default and access handlers."""

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(DefaultFormatter(DEFAULT_LOG_FORMAT, use_colors=config.use_colors))

    access_logger = logging.getLogger("palfrey.access")
    if access_logger.handlers:
        for handler in access_logger.handlers:
            handler.setFormatter(AccessFormatter(ACCESS_LOG_FORMAT, use_colors=config.use_colors))
    else:
        access_handler = logging.StreamHandler(sys.stdout)
        access_handler.setFormatter(
            AccessFormatter(ACCESS_LOG_FORMAT, use_colors=config.use_colors)
        )
        access_logger.addHandler(access_handler)
    access_logger.propagate = True


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
            payload = cast(dict[str, Any], log_config)
            if config.use_colors in (True, False):
                formatters = payload.get("formatters", {})
                if isinstance(formatters, dict):
                    for formatter_name in ("default", "access"):
                        formatter_config = formatters.get(formatter_name)
                        if isinstance(formatter_config, dict):
                            formatter_config["use_colors"] = config.use_colors
            logging.config.dictConfig(payload)
        elif isinstance(log_config, RawConfigParser):
            logging.config.fileConfig(log_config, disable_existing_loggers=False)
        elif hasattr(log_config, "read"):
            logging.config.fileConfig(cast(IO[str], log_config), disable_existing_loggers=False)
        else:
            path = Path(log_config)
            if path.suffix.lower() == ".json":
                with path.open("r", encoding="utf-8") as file:
                    payload_json: dict[str, Any] = json.load(file)
                logging.config.dictConfig(payload_json)
            elif path.suffix.lower() in {".yaml", ".yml"}:
                try:
                    import yaml
                except ImportError as exc:  # pragma: no cover - optional dependency branch.
                    raise RuntimeError(
                        "YAML log config requires PyYAML. Install optional dependencies."
                    ) from exc

                with path.open("r", encoding="utf-8") as file:
                    payload_yaml = yaml.safe_load(file)
                if not isinstance(payload_yaml, dict):
                    raise ValueError("YAML log config must deserialize to a dictionary.")
                logging.config.dictConfig(payload_yaml)
            else:
                logging.config.fileConfig(path, disable_existing_loggers=False)
    else:
        logging.basicConfig(
            level=_to_logging_level(config.log_level),
            format=DEFAULT_LOG_FORMAT,
            force=True,
        )
        _apply_default_formatters(config)

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
