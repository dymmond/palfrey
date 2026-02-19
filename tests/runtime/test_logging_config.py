from __future__ import annotations

import json
import logging
import types
from configparser import RawConfigParser
from pathlib import Path

import pytest

from palfrey.config import PalfreyConfig
from palfrey.logging_config import TRACE_LEVEL, configure_logging


def test_configure_logging_with_default_level() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_level="debug")
    configure_logging(config)
    logger = logging.getLogger("palfrey.test")
    assert logger.isEnabledFor(logging.DEBUG)


def test_configure_logging_from_json_file(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {"std": {"format": "%(levelname)s %(message)s"}},
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "std",
                        "stream": "ext://sys.stdout",
                    }
                },
                "root": {"level": "INFO", "handlers": ["console"]},
            }
        ),
        encoding="utf-8",
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    configure_logging(config)
    logger = logging.getLogger("palfrey.test")
    assert logger.isEnabledFor(logging.INFO)


def test_configure_logging_supports_trace_level() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_level="trace")
    configure_logging(config)
    error_logger = logging.getLogger("palfrey.error")
    assert error_logger.level == TRACE_LEVEL


def test_configure_logging_defaults_to_info_when_level_missing() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_level=None)
    configure_logging(config)
    error_logger = logging.getLogger("palfrey.error")
    assert error_logger.level == logging.INFO


def test_configure_logging_from_ini_file(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    parser = RawConfigParser()
    parser.read_dict(
        {
            "loggers": {"keys": "root"},
            "handlers": {"keys": "console"},
            "formatters": {"keys": "std"},
            "logger_root": {"level": "DEBUG", "handlers": "console"},
            "handler_console": {
                "class": "StreamHandler",
                "level": "DEBUG",
                "formatter": "std",
                "args": "(sys.stdout,)",
            },
            "formatter_std": {"format": "%(levelname)s %(message)s"},
        }
    )
    with config_path.open("w", encoding="utf-8") as file:
        parser.write(file)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    configure_logging(config)
    assert logging.getLogger().isEnabledFor(logging.DEBUG)


def test_configure_logging_from_yaml_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "logging.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    payload = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"std": {"format": "%(levelname)s %(message)s"}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "std",
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"level": "WARNING", "handlers": ["console"]},
    }
    fake_yaml = types.SimpleNamespace(safe_load=lambda _: payload)
    monkeypatch.setitem(__import__("sys").modules, "yaml", fake_yaml)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    configure_logging(config)
    assert logging.getLogger().isEnabledFor(logging.WARNING)


def test_configure_logging_yaml_requires_pyyaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "logging.yml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "yaml":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(__import__("sys").modules, "yaml", raising=False)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    with pytest.raises(RuntimeError, match="requires PyYAML"):
        configure_logging(config)
