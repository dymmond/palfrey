"""Internal server behavior tests."""

from __future__ import annotations

import asyncio
import ssl

import pytest

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.importer import ResolvedApp
from palfrey.protocols.http import HTTPRequest, HTTPResponse
from palfrey.server import PalfreyServer


class DummyWriter:
    def __init__(self, *, tls: bool = False) -> None:
        self.writes: list[bytes] = []
        self.closed = False
        self.drains = 0
        self._tls = tls

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        self.drains += 1

    def get_extra_info(self, name: str):
        if name == "peername":
            return ("127.0.0.1", 50000)
        if name == "sockname":
            return ("127.0.0.1", 8000)
        if name == "ssl_object":
            return object() if self._tls else None
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _resolved_app() -> ResolvedApp:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return ResolvedApp(app=app, interface="asgi3")


def test_normalize_address_from_tuple() -> None:
    host, port = PalfreyServer._normalize_address(
        ("127.0.0.1", 8000),
        default_host="x",
        default_port=1,
    )
    assert host == "127.0.0.1"
    assert port == 8000


def test_normalize_address_uses_defaults_for_unknown_type() -> None:
    host, port = PalfreyServer._normalize_address(
        "not-a-tuple",
        default_host="x",
        default_port=1,
    )
    assert host == "x"
    assert port == 1


def test_request_slot_limit_enforced() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=1)
    server = PalfreyServer(config)

    async def scenario() -> None:
        assert await server._enter_request_slot() is True
        assert await server._enter_request_slot() is False
        await server._leave_request_slot()
        assert await server._enter_request_slot() is True
        await server._leave_request_slot()

    asyncio.run(scenario())


def test_request_slot_unlimited_is_always_available() -> None:
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=None)
    )

    async def scenario() -> None:
        assert await server._enter_request_slot() is True
        await server._leave_request_slot()

    asyncio.run(scenario())


def test_service_unavailable_response_contains_default_body() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    response = server._service_unavailable_response()
    assert response.status == 503
    assert response.body_chunks == [b"Service Unavailable"]


def test_compute_max_requests_before_exit_none_when_not_configured() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    assert server._compute_max_requests_before_exit() is None


def test_compute_max_requests_before_exit_applies_jitter(monkeypatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=100,
        limit_max_requests_jitter=7,
    )
    server = PalfreyServer(config)
    monkeypatch.setattr(server_module.random, "randint", lambda start, end: 5)
    assert server._compute_max_requests_before_exit() == 105


def test_validate_protocol_backends_rejects_missing_httptools(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", http="httptools"))
    monkeypatch.setattr(server_module, "find_spec", lambda name: None)
    with pytest.raises(RuntimeError, match="httptools"):
        server._validate_protocol_backends()


def test_validate_protocol_backends_allows_missing_wsproto(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="wsproto"))

    def fake_find_spec(name: str):
        if name == "wsproto":
            return None
        return object()

    monkeypatch.setattr(server_module, "find_spec", fake_find_spec)
    server._validate_protocol_backends()


def test_build_ssl_context_returns_none_without_certfile() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    assert server._build_ssl_context() is None


def test_build_ssl_context_configures_certificate_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeContext:
        def __init__(self, version: int) -> None:
            captured["version"] = version

        def load_cert_chain(self, certfile: str, keyfile: str | None, password: str | None) -> None:
            captured["cert"] = certfile
            captured["key"] = keyfile
            captured["password"] = password

        def load_verify_locations(self, ca_certs: str) -> None:
            captured["ca"] = ca_certs

        def set_ciphers(self, ciphers: str) -> None:
            captured["ciphers"] = ciphers

        verify_mode = ssl.CERT_NONE

    monkeypatch.setattr(server_module.ssl, "SSLContext", FakeContext)

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
        ssl_keyfile_password="secret",
        ssl_ca_certs="ca.pem",
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        ssl_ciphers="ECDHE",
    )

    context = PalfreyServer(config)._build_ssl_context()
    assert isinstance(context, FakeContext)
    assert captured["cert"] == "cert.pem"
    assert captured["key"] == "key.pem"
    assert captured["password"] == "secret"
    assert captured["ca"] == "ca.pem"
    assert captured["ciphers"] == "ECDHE"
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_handle_connection_writes_400_on_bad_request(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._resolved_app = _resolved_app()
    writer = DummyWriter()

    async def fake_read_request(reader, **kwargs):
        raise ValueError("bad request")

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"400 Bad Request" in payload
    assert writer.closed is True


def test_handle_connection_writes_500_on_unhandled_exception(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._resolved_app = _resolved_app()
    writer = DummyWriter()

    async def fake_read_request(reader, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"500 Internal Server Error" in payload
    assert writer.closed is True


def test_handle_connection_switches_to_websocket_upgrade(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="websockets"))
    server._resolved_app = _resolved_app()
    writer = DummyWriter()
    called: list[str] = []
    request = HTTPRequest(
        method="GET",
        target="/ws",
        http_version="HTTP/1.1",
        headers=[("upgrade", "websocket"), ("connection", "Upgrade")],
        body=b"",
    )

    calls = {"count": 0}

    async def fake_read_request(reader, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return request
        return None

    async def fake_handle_websocket(*args, **kwargs):
        called.append("ws")

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(server_module, "is_websocket_upgrade", lambda req: True)
    monkeypatch.setattr(server_module, "handle_websocket", fake_handle_websocket)

    asyncio.run(server._handle_connection(object(), writer))

    assert called == ["ws"]
    assert writer.closed is True


def test_handle_connection_sends_100_continue_and_respects_max_requests(monkeypatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=1,
        timeout_keep_alive=1,
    )
    server = PalfreyServer(config)
    server._resolved_app = _resolved_app()
    writer = DummyWriter()
    request = HTTPRequest(
        method="POST",
        target="/submit",
        http_version="HTTP/1.1",
        headers=[("expect", "100-continue")],
        body=b"hello",
    )
    calls = {"count": 0}

    async def fake_read_request(reader, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return request
        return None

    async def fake_handle_http_request(
        self: PalfreyServer, request: HTTPRequest, context
    ) -> HTTPResponse:
        return HTTPResponse(
            status=200, headers=[(b"content-type", b"text/plain")], body_chunks=[b"ok"]
        )

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(PalfreyServer, "_handle_http_request", fake_handle_http_request)
    monkeypatch.setattr(server_module, "should_keep_alive", lambda request, response: False)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"100 Continue" in payload
    assert b"200 OK" in payload
    assert server._shutdown_event.is_set() is True


def test_handle_connection_returns_503_when_concurrency_limit_reached(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=0))
    server._resolved_app = _resolved_app()
    writer = DummyWriter()
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )
    calls = {"count": 0}

    async def fake_read_request(reader, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return request
        return None

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"503 Service Unavailable" in payload
