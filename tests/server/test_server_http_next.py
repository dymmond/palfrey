from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPRequest, HTTPResponse
from palfrey.server import ConnectionContext, PalfreyServer


class _Writer:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def get_extra_info(self, name: str):
        if name == "peername":
            return ("127.0.0.1", 50123)
        if name == "sockname":
            return ("127.0.0.1", 8000)
        if name == "ssl_object":
            return object()
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed


def _resolved() -> SimpleNamespace:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return SimpleNamespace(app=app, interface="asgi3")


def test_validate_protocol_backends_rejects_missing_h2(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", http="h2"))

    def fake_find_spec(name: str):
        if name == "h2":
            return None
        return object()

    monkeypatch.setattr(server_module, "find_spec", fake_find_spec)
    with pytest.raises(RuntimeError, match="HTTP mode 'h2'"):
        server._validate_protocol_backends()


def test_validate_protocol_backends_rejects_missing_aioquic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ws="none",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
        )
    )

    def fake_find_spec(name: str):
        if name == "aioquic":
            return None
        return object()

    monkeypatch.setattr(server_module, "find_spec", fake_find_spec)
    with pytest.raises(RuntimeError, match="HTTP mode 'h3' requires the 'aioquic' package"):
        server._validate_protocol_backends()


def test_validate_protocol_backends_rejects_h3_without_tls_files() -> None:
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ws="none",
        )
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_module, "find_spec", lambda _name: object())
        with pytest.raises(RuntimeError, match="requires both --ssl-certfile and --ssl-keyfile"):
            server._validate_protocol_backends()


def test_validate_protocol_backends_rejects_h3_fd_and_uds(monkeypatch: pytest.MonkeyPatch) -> None:
    server_fd = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ws="none",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
            fd=3,
        )
    )
    server_uds = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ws="none",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
            uds="/tmp/palfrey.sock",
        )
    )
    monkeypatch.setattr(server_module, "find_spec", lambda _name: object())

    with pytest.raises(RuntimeError, match="does not support --fd or --uds"):
        server_fd._validate_protocol_backends()
    with pytest.raises(RuntimeError, match="does not support --fd or --uds"):
        server_uds._validate_protocol_backends()


def test_build_ssl_context_sets_h2_alpn(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.protocols: list[list[str]] = []

        def set_alpn_protocols(self, values: list[str]) -> None:
            self.protocols.append(values)

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="h2",
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
    )
    server = PalfreyServer(config)
    monkeypatch.setattr(server_module, "create_ssl_context", lambda **_kwargs: FakeContext())

    context = server._build_ssl_context()
    assert isinstance(context, FakeContext)
    assert context.protocols == [["h2"]]


def test_handle_connection_routes_http2_to_protocol_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", http="h2"))
    server._resolved_app = _resolved()  # type: ignore[assignment]
    writer = _Writer()
    called: dict[str, object] = {}

    async def fake_serve_http2_connection(*, reader, writer, request_handler):
        called["reader"] = reader
        called["writer"] = writer
        request = HTTPRequest(
            method="GET",
            target="/h2",
            http_version="HTTP/2",
            headers=[("host", "localhost")],
            body=b"",
        )
        response = await request_handler(request)
        called["status"] = response.status

    async def fake_handle_http_request(
        self: PalfreyServer,
        request: HTTPRequest,
        context: ConnectionContext,
    ) -> HTTPResponse:
        assert request.http_version == "HTTP/2"
        assert context.client == ("127.0.0.1", 50123)
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    monkeypatch.setattr(server_module, "serve_http2_connection", fake_serve_http2_connection)
    monkeypatch.setattr(PalfreyServer, "_handle_http_request", fake_handle_http_request)

    asyncio.run(server._handle_connection(object(), writer))  # type: ignore[arg-type]

    assert called["writer"] is writer
    assert called["status"] == 200
    assert writer.closed is True
    assert server.server_state.total_requests == 1


def test_serve_http3_path_uses_http3_server_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    events: dict[str, object] = {}

    class FakeLoop:
        def add_signal_handler(self, _sig, _callback) -> None:
            return None

    class FakeServer:
        def __init__(self) -> None:
            self.closed = False
            self.wait_closed_called = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            self.wait_closed_called = True

    fake_server = FakeServer()

    def fake_load(self: PalfreyConfig) -> None:
        resolved = _resolved()
        self.loaded_app = resolved.app
        self.interface = resolved.interface
        self.lifespan_class = None
        self.loaded = True

    async def fake_create_http3_server(*, config, request_handler):
        events["config"] = config
        events["handler"] = request_handler
        return fake_server

    monkeypatch.setattr(PalfreyConfig, "load", fake_load)
    monkeypatch.setattr(server_module, "configure_logging", lambda _config: None)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(server_module, "create_http3_server", fake_create_http3_server)
    monkeypatch.setattr(server_module, "find_spec", lambda _name: object())

    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ws="none",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
            lifespan="off",
        )
    )
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert events["config"] is server.config
    assert fake_server.closed is True
    assert fake_server.wait_closed_called is True
