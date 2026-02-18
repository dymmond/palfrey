"""Additional logging config parity tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import palfrey.logging_config as logging_config_module
from palfrey.config import PalfreyConfig
from palfrey.logging_config import TRACE_LEVEL, _to_logging_level, configure_logging


def test_to_logging_level_trace_maps_to_trace_level() -> None:
    assert _to_logging_level("trace") == TRACE_LEVEL


def test_to_logging_level_unknown_defaults_to_info() -> None:
    assert _to_logging_level("not-a-level") == logging.INFO


def test_to_logging_level_integer_passes_through() -> None:
    assert _to_logging_level(7) == 7


def test_configure_logging_with_dict_payload_uses_dictconfig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"default": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["default"], "level": "INFO"},
    }
    captured: dict[str, object] = {}

    def fake_dictconfig(value):
        captured["payload"] = value

    monkeypatch.setattr(logging_config_module.logging.config, "dictConfig", fake_dictconfig)

    configure_logging(PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=payload))
    assert captured["payload"] == payload


def test_configure_logging_with_json_file_uses_dictconfig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"default": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["default"], "level": "INFO"},
    }
    config_path = tmp_path / "logging.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_dictconfig(value):
        captured["payload"] = value

    monkeypatch.setattr(logging_config_module.logging.config, "dictConfig", fake_dictconfig)

    configure_logging(
        PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    )
    assert captured["payload"] == payload


def test_configure_logging_with_yaml_requires_dict_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "logging.yaml"
    config_path.write_text("- not-a-dict\n", encoding="utf-8")

    class FakeYAML:
        @staticmethod
        def safe_load(content):
            return ["not-a-dict"]

    monkeypatch.setitem(__import__("sys").modules, "yaml", FakeYAML)

    with pytest.raises(ValueError, match="must deserialize to a dictionary"):
        configure_logging(
            PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
        )


def test_configure_logging_with_ini_uses_file_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text("[loggers]\nkeys=root\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_file_config(path, disable_existing_loggers=False):
        captured["path"] = path
        captured["disable"] = disable_existing_loggers

    monkeypatch.setattr(logging_config_module.logging.config, "fileConfig", fake_file_config)
    configure_logging(
        PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    )
    assert captured["path"] == config_path
    assert captured["disable"] is False


def test_configure_logging_basic_config_uses_provided_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_basic_config(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(logging_config_module.logging, "basicConfig", fake_basic_config)
    configure_logging(PalfreyConfig(app="tests.fixtures.apps:http_app", log_level="debug"))
    assert captured["level"] == logging.DEBUG
    assert captured["force"] is True
