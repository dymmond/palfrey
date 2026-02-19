"""Runtime run(...) API parity tests."""

from __future__ import annotations

import asyncio
import ssl
from pathlib import Path

import pytest

import palfrey.runtime as runtime_module
from palfrey.config import PalfreyConfig
from palfrey.runtime import run


class _RuntimeHTTPProtocol(asyncio.Protocol):
    """Dummy protocol class for runtime API parity tests."""


class _RuntimeWSProtocol(asyncio.Protocol):
    """Dummy websocket protocol class for runtime API parity tests."""


def test_run_forwards_uvicorn_style_kwargs_into_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[PalfreyConfig] = []

    def fake_run_config(config: PalfreyConfig):
        captured.append(config)
        return None

    monkeypatch.setattr(runtime_module, "_run_config", fake_run_config)

    run(
        "tests.fixtures.apps:http_app",
        host="0.0.0.0",
        port=9000,
        loop="tests.loops.custom_loop_factory:setup_loop",
        http="h11",
        ws="wsproto",
        ws_max_size=1024,
        ws_max_queue=64,
        ws_ping_interval=10.0,
        ws_ping_timeout=12.0,
        ws_per_message_deflate=False,
        lifespan="on",
        interface="asgi3",
        reload=False,
        reload_dirs=["src"],
        reload_includes=["*.py"],
        reload_excludes=["*.tmp"],
        reload_delay=0.5,
        workers=1,
        env_file=None,
        log_config=None,
        log_level="debug",
        access_log=False,
        use_colors=True,
        proxy_headers=False,
        server_header=False,
        date_header=False,
        forwarded_allow_ips="*",
        root_path="/api",
        limit_concurrency=32,
        backlog=4096,
        limit_max_requests=100,
        limit_max_requests_jitter=7,
        timeout_keep_alive=8,
        timeout_notify=15,
        timeout_graceful_shutdown=20,
        timeout_worker_healthcheck=9,
        ssl_keyfile="key.pem",
        ssl_certfile="cert.pem",
        ssl_keyfile_password="secret",
        ssl_version=33,
        ssl_cert_reqs=1,
        ssl_ca_certs="ca.pem",
        ssl_ciphers="ECDHE",
        headers=[("x-test", "1")],
        app_dir=".",
        factory=True,
        h11_max_incomplete_event_size=8192,
    )

    config = captured[0]
    assert config.host == "0.0.0.0"
    assert config.port == 9000
    assert config.loop == "tests.loops.custom_loop_factory:setup_loop"
    assert config.http == "h11"
    assert config.ws == "wsproto"
    assert config.ws_max_size == 1024
    assert config.ws_max_queue == 64
    assert config.ws_ping_interval == 10.0
    assert config.ws_ping_timeout == 12.0
    assert config.ws_per_message_deflate is False
    assert config.interface == "asgi3"
    assert config.reload_dirs == ["src"]
    assert config.reload_includes == ["*.py"]
    assert config.reload_excludes == ["*.tmp"]
    assert config.reload_delay == 0.5
    assert config.log_level == "debug"
    assert config.access_log is False
    assert config.use_colors is True
    assert config.proxy_headers is False
    assert config.server_header is False
    assert config.date_header is False
    assert config.forwarded_allow_ips == "*"
    assert config.root_path == "/api"
    assert config.limit_concurrency == 32
    assert config.backlog == 4096
    assert config.limit_max_requests == 100
    assert config.limit_max_requests_jitter == 7
    assert config.timeout_keep_alive == 8
    assert config.timeout_notify == 15
    assert config.timeout_graceful_shutdown == 20
    assert config.timeout_worker_healthcheck == 9
    assert config.ssl_keyfile == "key.pem"
    assert config.ssl_certfile == "cert.pem"
    assert config.ssl_keyfile_password == "secret"
    assert config.ssl_version == 33
    assert config.ssl_cert_reqs == 1
    assert config.ssl_ca_certs == "ca.pem"
    assert config.ssl_ciphers == "ECDHE"
    assert config.normalized_headers == [("x-test", "1")]
    assert config.factory is True
    assert config.h11_max_incomplete_event_size == 8192


def test_run_normalizes_string_reload_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []
    monkeypatch.setattr(
        runtime_module,
        "_run_config",
        lambda config: captured.append(config) or None,
    )

    run(
        "tests.fixtures.apps:http_app",
        reload_dirs="src",
        reload_includes="*.py",
        reload_excludes="*.tmp",
    )

    config = captured[0]
    assert config.reload_dirs == ["src"]
    assert config.reload_includes == ["*.py"]
    assert config.reload_excludes == ["*.tmp"]


def test_run_default_ssl_values_match_uvicorn_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []
    monkeypatch.setattr(
        runtime_module,
        "_run_config",
        lambda config: captured.append(config) or None,
    )

    run("tests.fixtures.apps:http_app")
    config = captured[0]
    assert config.ssl_version == int(ssl.PROTOCOL_TLS_SERVER)
    assert config.ssl_cert_reqs == int(ssl.CERT_NONE)


def test_run_converts_pathlike_ssl_inputs_to_string(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []
    monkeypatch.setattr(
        runtime_module,
        "_run_config",
        lambda config: captured.append(config) or None,
    )

    run(
        "tests.fixtures.apps:http_app",
        ssl_keyfile=Path("key.pem"),
        ssl_certfile=Path("cert.pem"),
        ssl_ca_certs=Path("ca.pem"),
    )
    config = captured[0]
    assert config.ssl_keyfile == "key.pem"
    assert config.ssl_certfile == "cert.pem"
    assert config.ssl_ca_certs == "ca.pem"


def test_run_accepts_concrete_protocol_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []
    monkeypatch.setattr(
        runtime_module,
        "_run_config",
        lambda config: captured.append(config) or None,
    )

    run(
        "tests.fixtures.apps:http_app",
        http=_RuntimeHTTPProtocol,
        ws=_RuntimeWSProtocol,
    )

    config = captured[0]
    assert config.http is _RuntimeHTTPProtocol
    assert config.ws is _RuntimeWSProtocol
