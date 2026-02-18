"""Configuration behavior tests modeled after Uvicorn config expectations."""

from __future__ import annotations

from pathlib import Path

import pytest

from palfrey.config import PalfreyConfig


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [(None, 1), ("2", 2), ("8", 8)],
)
def test_workers_default_from_web_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
    expected: int,
) -> None:
    if env_value is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", env_value)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.workers_count == expected


def test_workers_explicit_value_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "9")
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=3)
    assert config.workers_count == 3


@pytest.mark.parametrize("workers", [0, -1])
def test_workers_must_be_positive(workers: int) -> None:
    with pytest.raises(ValueError, match="workers must be >= 1"):
        PalfreyConfig(app="tests.fixtures.apps:http_app", workers=workers)


def test_forwarded_allow_ips_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1,127.0.0.1")
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.forwarded_allow_ips == "10.0.0.1,127.0.0.1"


def test_forwarded_allow_ips_default_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    assert config.forwarded_allow_ips == "127.0.0.1"


def test_reload_populates_default_reload_dir(tmp_path: Path) -> None:
    current = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
        assert config.reload_dirs == [str(tmp_path)]
    finally:
        os.chdir(current)


def test_app_dir_is_normalized(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        app_dir=str(nested / ".." / "nested"),
    )
    assert config.app_dir == str(nested.resolve())


def test_normalized_headers_accepts_tuple_values() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=[("x-trace", "abc")])
    assert config.normalized_headers == [("x-trace", "abc")]


def test_normalized_headers_accepts_string_values() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["x-one: 1", "x-two: 2"])
    assert config.normalized_headers == [("x-one", "1"), ("x-two", "2")]


def test_limit_max_requests_jitter_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="limit_max_requests_jitter must be >= 0"):
        PalfreyConfig(app="tests.fixtures.apps:http_app", limit_max_requests_jitter=-1)


def test_from_import_string_builds_config() -> None:
    config = PalfreyConfig.from_import_string(
        "tests.fixtures.apps:http_app",
        host="0.0.0.0",
        port=9000,
        workers=2,
    )
    assert config.host == "0.0.0.0"
    assert config.port == 9000
    assert config.workers_count == 2
