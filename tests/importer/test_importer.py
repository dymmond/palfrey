"""Importer and interface resolution tests."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

from palfrey.config import PalfreyConfig
from palfrey.importer import AppImportError, resolve_application
from palfrey.middleware.message_logger import MessageLoggerMiddleware
from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware


async def asgi3_app(scope, receive, send):
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


class ASGI2App:
    def __call__(self, scope):
        async def app(receive, send):
            if scope["type"] == "http":
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ok"})

        return app


def test_resolve_import_string() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    resolved = resolve_application(config)
    assert callable(resolved.app)


def test_resolve_asgi2_interface() -> None:
    config = PalfreyConfig(app=ASGI2App(), interface="asgi2")
    resolved = resolve_application(config)
    assert resolved.interface == "asgi2"


def test_resolve_wsgi_interface() -> None:
    def wsgi_app(environ: dict[str, Any], start_response):
        start_response("200 OK", [("content-type", "text/plain")])
        return [b"ok"]

    config = PalfreyConfig(app=wsgi_app, interface="wsgi")
    resolved = resolve_application(config)
    assert resolved.interface == "wsgi"


def test_resolve_factory() -> None:
    def factory():
        return asgi3_app

    config = PalfreyConfig(app=factory, factory=True)
    resolved = resolve_application(config)
    assert callable(resolved.app)


def test_resolve_wraps_proxy_headers_middleware_when_enabled() -> None:
    config = PalfreyConfig(app=asgi3_app, proxy_headers=True)
    resolved = resolve_application(config)
    assert isinstance(resolved.app, ProxyHeadersMiddleware)


def test_invalid_import_string_raises() -> None:
    config = PalfreyConfig(app="broken-import-string")
    with pytest.raises(AppImportError):
        resolve_application(config)


def test_factory_requires_callable() -> None:
    config = PalfreyConfig(app=42, factory=True)
    with pytest.raises(AppImportError):
        resolve_application(config)


def test_resolve_import_string_missing_module_reports_original_error() -> None:
    config = PalfreyConfig(app="doesnotexist.module:app")
    with pytest.raises(AppImportError, match="Original error"):
        resolve_application(config)


def test_resolve_import_string_missing_attribute() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:not_there")
    with pytest.raises(AppImportError, match="does not expose attribute"):
        resolve_application(config)


def test_invalid_factory_result_is_rejected() -> None:
    def factory():
        return 123

    config = PalfreyConfig(app=factory, factory=True)
    with pytest.raises(AppImportError, match="Resolved WSGI app is not callable"):
        resolve_application(config)


def test_invalid_interface_mode_is_rejected() -> None:
    config = PalfreyConfig(app=asgi3_app)
    config.interface = "invalid"  # type: ignore[assignment]
    with pytest.raises(AppImportError, match="Unsupported interface mode"):
        resolve_application(config)


def test_trace_log_level_wraps_message_logger_middleware() -> None:
    config = PalfreyConfig(app=asgi3_app, log_level="trace")
    resolved = resolve_application(config)
    assert isinstance(resolved.app, MessageLoggerMiddleware)


def test_default_app_dir_resolves_current_working_directory(tmp_path) -> None:
    module_file = tmp_path / "demoapp.py"
    module_file.write_text(
        (
            "async def app(scope, receive, send):\n"
            "    if scope['type'] == 'http':\n"
            "        await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
            "        await send({'type': 'http.response.body', 'body': b'ok'})\n"
        ),
        encoding="utf-8",
    )

    current = os.getcwd()
    original_sys_path = list(sys.path)
    try:
        os.chdir(tmp_path)
        sys.path = [item for item in sys.path if str(tmp_path) not in str(item)]

        config = PalfreyConfig(app="demoapp:app")
        resolved = resolve_application(config)
        assert callable(resolved.app)
    finally:
        os.chdir(current)
        sys.path = original_sys_path
