from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import palfrey.logging_config as logging_config_module
from palfrey.config import PalfreyConfig
from palfrey.logging_config import (
    TRACE_LEVEL,
    AccessFormatter,
    DefaultFormatter,
    _to_logging_level,
    configure_logging,
)


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


def test_configure_logging_with_dict_payload_applies_log_level_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"default": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["default"], "level": "INFO"},
    }
    monkeypatch.setattr(logging_config_module.logging.config, "dictConfig", lambda _value: None)
    monkeypatch.setattr(
        logging_config_module.logging.config,
        "fileConfig",
        lambda *_args, **_kwargs: None,
    )

    configure_logging(
        PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=payload, log_level="debug")
    )
    assert logging.getLogger("palfrey.error").level == logging.DEBUG
    assert logging.getLogger("palfrey.access").level == logging.DEBUG
    assert logging.getLogger("palfrey.asgi").level == logging.DEBUG


def test_configure_logging_with_dict_payload_disables_access_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"default": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["default"], "level": "INFO"},
        "loggers": {
            "palfrey.access": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": True,
            }
        },
    }
    monkeypatch.setattr(logging_config_module.logging.config, "dictConfig", lambda _value: None)

    access_logger = logging.getLogger("palfrey.access")
    access_logger.handlers = [logging.NullHandler()]
    access_logger.propagate = True

    configure_logging(
        PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=payload, access_log=False)
    )
    assert access_logger.handlers == []
    assert access_logger.propagate is False


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
    configure_logging(
        PalfreyConfig(app="tests.fixtures.apps:http_app", log_level="debug", log_config=None)
    )
    assert captured["level"] == logging.DEBUG
    assert captured["force"] is True


def test_default_formatter_includes_levelprefix_without_color() -> None:
    formatter = DefaultFormatter("%(levelprefix)s %(message)s", use_colors=False)
    record = logging.LogRecord(
        name="palfrey.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    rendered = formatter.format(record)
    assert rendered.startswith("INFO:")
    assert rendered.endswith("hello")


def test_access_formatter_renders_status_phrase_without_color() -> None:
    formatter = AccessFormatter(
        "%(client_addr)s %(request_line)s %(status_code)s", use_colors=False
    )
    record = logging.LogRecord(
        name="palfrey.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %s',
        args=("127.0.0.1", "GET", "/items", "1.1", 200),
        exc_info=None,
    )
    rendered = formatter.format(record)
    assert "127.0.0.1" in rendered
    assert "GET /items HTTP/1.1" in rendered
    assert "200 OK" in rendered
