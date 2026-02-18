"""Additional runtime/helper coverage tests."""

from __future__ import annotations

import io
import logging
import os
from configparser import RawConfigParser
from pathlib import Path

import pytest

import palfrey.acceleration as acceleration
import palfrey.logging_config as logging_config_module
from palfrey.config import PalfreyConfig
from palfrey.env import load_env_file
from palfrey.logging_config import configure_logging


def test_load_env_file_skips_comments_blank_and_invalid_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n# comment\nINVALID\nGOOD=1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GOOD", raising=False)
    load_env_file(env_file)
    assert os.environ["GOOD"] == "1"


def test_configure_logging_accepts_raw_config_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = RawConfigParser()
    captured: dict[str, object] = {}

    def fake_file_config(target, disable_existing_loggers=False):
        captured["target"] = target
        captured["disable"] = disable_existing_loggers

    monkeypatch.setattr(logging_config_module.logging.config, "fileConfig", fake_file_config)
    configure_logging(PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=parser))
    assert captured["target"] is parser
    assert captured["disable"] is False


def test_configure_logging_accepts_file_like_object(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO("[loggers]\nkeys=root\n")
    captured: dict[str, object] = {}

    def fake_file_config(target, disable_existing_loggers=False):
        captured["target"] = target
        captured["disable"] = disable_existing_loggers

    monkeypatch.setattr(logging_config_module.logging.config, "fileConfig", fake_file_config)
    configure_logging(PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=stream))
    assert captured["target"] is stream
    assert captured["disable"] is False


def test_configure_logging_disables_access_logger_handlers() -> None:
    access_logger = logging.getLogger("palfrey.access")
    original_handlers = list(access_logger.handlers)
    original_propagate = access_logger.propagate
    try:
        configure_logging(PalfreyConfig(app="tests.fixtures.apps:http_app", access_log=False))
        assert access_logger.handlers == []
        assert access_logger.propagate is False
    finally:
        access_logger.handlers = original_handlers
        access_logger.propagate = original_propagate


def test_acceleration_rust_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", True)
    monkeypatch.setattr(acceleration, "_split_csv_values", lambda value: ["a", "b"])
    monkeypatch.setattr(
        acceleration, "_parse_request_head", lambda data: ("GET", "/", "HTTP/1.1", [])
    )
    monkeypatch.setattr(
        acceleration,
        "_parse_header_items",
        lambda headers: [("x-a", "1"), ("x-b", "2")],
    )

    assert acceleration.split_csv_values("x") == ["a", "b"]
    assert acceleration.parse_request_head(b"GET / HTTP/1.1\r\n\r\n") == (
        "GET",
        "/",
        "HTTP/1.1",
        [],
    )
    assert acceleration.parse_header_items(["x-a:1", "x-b:2"]) == [("x-a", "1"), ("x-b", "2")]


def test_acceleration_rust_header_error_maps_to_header_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", True)

    def fake_parse(_: list[str]) -> list[tuple[str, str]]:
        raise ValueError("invalid")

    monkeypatch.setattr(acceleration, "_parse_header_items", fake_parse)
    with pytest.raises(acceleration.HeaderParseError, match="invalid"):
        acceleration.parse_header_items(["broken"])
