"""Additional config parity tests inspired by Uvicorn config coverage."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from palfrey.config import PalfreyConfig


def test_config_default_workers_is_one_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.workers == 1


def test_config_workers_parses_web_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.workers == 4


def test_config_forwarded_allow_ips_uses_explicit_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        forwarded_allow_ips="10.0.0.1,10.0.0.2",
    )
    assert config.forwarded_allow_ips == "10.0.0.1,10.0.0.2"


def test_config_reload_does_not_set_dirs_when_disabled() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=False, reload_dirs=[])
    assert config.reload_dirs == []


def test_config_reload_keeps_user_provided_dirs(tmp_path: Path) -> None:
    target = tmp_path / "watch"
    target.mkdir()
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(target)],
    )
    assert config.reload_dirs == [str(target)]


def test_config_default_app_dir_is_resolved_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    previous = Path.cwd()
    try:
        monkeypatch.chdir(tmp_path)
        config = PalfreyConfig(app="tests.fixtures.apps:http_app")
        assert config.app_dir == str(tmp_path.resolve())
    finally:
        monkeypatch.chdir(previous)


def test_config_ssl_defaults_match_uvicorn_baseline() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.ssl_version == int(ssl.PROTOCOL_TLS_SERVER)
    assert config.ssl_cert_reqs == int(ssl.CERT_NONE)


def test_config_normalized_headers_strips_whitespace() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["X-Test:   value"])
    assert config.normalized_headers == [("X-Test", "value")]


def test_config_normalized_headers_tuple_values_are_stringified() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=[("x-num", 123)])  # type: ignore[list-item]
    assert config.normalized_headers == [("x-num", "123")]


def test_config_normalized_headers_empty_when_unset() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.normalized_headers == []


def test_config_workers_count_property_returns_workers_value() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=3)
    assert config.workers_count == 3


def test_config_from_import_string_preserves_extra_kwargs() -> None:
    config = PalfreyConfig.from_import_string(
        "tests.fixtures.apps:http_app",
        root_path="/api",
        proxy_headers=False,
        access_log=False,
    )
    assert config.root_path == "/api"
    assert config.proxy_headers is False
    assert config.access_log is False


def test_config_invalid_negative_jitter_is_rejected() -> None:
    with pytest.raises(ValueError, match="limit_max_requests_jitter must be >= 0"):
        PalfreyConfig(app="tests.fixtures.apps:http_app", limit_max_requests_jitter=-10)


def test_config_invalid_worker_count_zero_is_rejected() -> None:
    with pytest.raises(ValueError, match="workers must be >= 1"):
        PalfreyConfig(app="tests.fixtures.apps:http_app", workers=0)


def test_config_reload_delay_value_is_preserved() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True, reload_delay=0.5)
    assert config.reload_delay == 0.5


def test_config_app_dir_from_import_string_path_object(tmp_path: Path) -> None:
    config = PalfreyConfig.from_import_string(
        "tests.fixtures.apps:http_app",
        app_dir=tmp_path,
    )
    assert config.app_dir == str(tmp_path.resolve())
