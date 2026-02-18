"""Additional server behavior tests aligned with Uvicorn server expectations."""

from __future__ import annotations

import asyncio
import logging

import pytest

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.importer import ResolvedApp
from palfrey.protocols.http import HTTPRequest, HTTPResponse
from palfrey.server import ConnectionContext, PalfreyServer


class DummyWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def get_extra_info(self, name: str):
        if name == "peername":
            return ("127.0.0.1", 50000)
        if name == "sockname":
            return ("127.0.0.1", 8000)
        if name == "ssl_object":
            return None
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _resolved_http_app() -> ResolvedApp:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    return ResolvedApp(app=app, interface="asgi3")


def test_compute_max_requests_before_exit_without_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=10,
        limit_max_requests_jitter=0,
    )
    server = PalfreyServer(config)
    monkeypatch.setattr(server_module.random, "randint", lambda start, end: 0)
    assert server._compute_max_requests_before_exit() == 10


def test_compute_max_requests_before_exit_with_max_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=10,
        limit_max_requests_jitter=5,
    )
    server = PalfreyServer(config)
    monkeypatch.setattr(server_module.random, "randint", lambda start, end: 5)
    assert server._compute_max_requests_before_exit() == 15


def test_normalize_address_invalid_port_uses_default() -> None:
    host, port = PalfreyServer._normalize_address(
        ("127.0.0.1", "not-a-port"),
        default_host="0.0.0.0",
        default_port=7000,
    )
    assert host == "127.0.0.1"
    assert port == 7000


def test_handle_http_request_access_log_includes_query_string(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", access_log=True))
    server._resolved_app = _resolved_http_app()
    request = HTTPRequest(
        method="GET",
        target="/items?limit=10",
        http_version="HTTP/1.1",
        headers=[("host", "example.test")],
        body=b"",
    )

    async def fake_run_http_asgi(app, scope, body):
        return HTTPResponse(status=204, headers=[], body_chunks=[])

    monkeypatch.setattr(server_module, "run_http_asgi", fake_run_http_asgi)
    caplog.set_level(logging.INFO, logger="palfrey.access")

    response = asyncio.run(
        server._handle_http_request(
            request,
            ConnectionContext(
                client=("127.0.0.1", 1111),
                server=("127.0.0.1", 8000),
                is_tls=False,
            ),
        )
    )

    assert response.status == 204
    assert '"GET /items?limit=10 HTTP/1.1" 204' in caplog.text


def test_handle_http_request_skips_access_log_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", access_log=False))
    server._resolved_app = _resolved_http_app()
    request = HTTPRequest(
        method="GET",
        target="/quiet",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )

    async def fake_run_http_asgi(app, scope, body):
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    monkeypatch.setattr(server_module, "run_http_asgi", fake_run_http_asgi)
    caplog.set_level(logging.INFO, logger="palfrey.access")

    asyncio.run(
        server._handle_http_request(
            request,
            ConnectionContext(
                client=("127.0.0.1", 1111),
                server=("127.0.0.1", 8000),
                is_tls=False,
            ),
        )
    )

    assert '"GET /quiet HTTP/1.1"' not in caplog.text


def test_handle_connection_respects_keep_alive_for_multiple_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._resolved_app = _resolved_http_app()
    writer = DummyWriter()
    req1 = HTTPRequest(method="GET", target="/one", http_version="HTTP/1.1", headers=[], body=b"")
    req2 = HTTPRequest(method="GET", target="/two", http_version="HTTP/1.1", headers=[], body=b"")
    calls = {"count": 0}

    async def fake_read_request(reader, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return req1
        if calls["count"] == 2:
            return req2
        return None

    async def fake_handle_request(self, request, context):
        return HTTPResponse(
            status=200, headers=[(b"content-type", b"text/plain")], body_chunks=[b"ok"]
        )

    keep_alive_plan = iter([True, False])
    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(PalfreyServer, "_handle_http_request", fake_handle_request)
    monkeypatch.setattr(
        server_module, "should_keep_alive", lambda request, response: next(keep_alive_plan)
    )

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert payload.count(b"HTTP/1.1 200 OK") == 2


def test_handle_connection_closes_on_keep_alive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", timeout_keep_alive=0))
    server._resolved_app = _resolved_http_app()
    writer = DummyWriter()

    async def fake_read_request(reader, **kwargs):
        await asyncio.sleep(0.01)
        return None

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    asyncio.run(server._handle_connection(object(), writer))
    assert writer.closed is True
