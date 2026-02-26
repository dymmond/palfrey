from __future__ import annotations

import asyncio
import logging
import ssl

import pytest

import palfrey.config as config_module
import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.importer import ResolvedApp
from palfrey.protocols.http import HTTPRequest
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


class _SocketWithName:
    def __init__(self, sockname: object) -> None:
        self._sockname = sockname

    def getsockname(self) -> object:
        return self._sockname


def test_loop_backend_name_returns_asyncio_for_stdlib_module_name() -> None:
    fake_loop_class = type("SelectorEventLoop", (), {"__module__": "asyncio.unix_events"})
    fake_loop = fake_loop_class()
    assert PalfreyServer._loop_backend_name(fake_loop) == "asyncio"  # type: ignore[arg-type]


def test_loop_backend_name_returns_uvloop_for_uvloop_module_name() -> None:
    fake_loop_class = type("Loop", (), {"__module__": "uvloop.loop"})
    fake_loop = fake_loop_class()
    assert PalfreyServer._loop_backend_name(fake_loop) == "uvloop"  # type: ignore[arg-type]


def test_loop_backend_name_returns_qualified_name_for_custom_loops() -> None:
    fake_loop_class = type("Loop", (), {"__module__": "custom.runtime"})
    fake_loop = fake_loop_class()
    assert PalfreyServer._loop_backend_name(fake_loop) == "custom.runtime.Loop"  # type: ignore[arg-type]


def test_log_runtime_configuration_emits_backend_summary() -> None:
    fake_loop_class = type("Loop", (), {"__module__": "uvloop.loop"})
    fake_loop = fake_loop_class()
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h11",
            ws="wsproto",
            lifespan="on",
            interface="asgi3",
        )
    )

    messages: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    server_logger = logging.getLogger("palfrey.server")
    previous_level = server_logger.level
    server_logger.setLevel(logging.INFO)
    capture_handler = _CaptureHandler()
    capture_handler.setLevel(logging.INFO)
    server_logger.addHandler(capture_handler)
    try:
        server._log_runtime_configuration(fake_loop)  # type: ignore[arg-type]
    finally:
        server_logger.removeHandler(capture_handler)
        server_logger.setLevel(previous_level)

    assert (
        "Runtime configuration: loop=uvloop, http=h11, ws=wsproto, lifespan=on, interface=asgi3"
        in messages
    )


def test_log_running_messages_deduplicates_targets() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    sockets = [
        _SocketWithName(("127.0.0.1", 8000)),
        _SocketWithName(("127.0.0.1", 8000)),
    ]

    running_lines: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            message = record.getMessage()
            if "Palfrey running on" in message:
                running_lines.append(message)

    server_logger = logging.getLogger("palfrey.server")
    previous_level = server_logger.level
    server_logger.setLevel(logging.INFO)
    capture_handler = _CaptureHandler()
    capture_handler.setLevel(logging.INFO)
    server_logger.addHandler(capture_handler)
    try:
        server._log_running_messages(sockets)  # type: ignore[arg-type]
    finally:
        server_logger.removeHandler(capture_handler)
        server_logger.setLevel(previous_level)

    assert running_lines == ["Palfrey running on http://127.0.0.1:8000 (Press CTRL+C to quit)"]


def test_format_running_target_wraps_ipv6_host() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    socket_with_ipv6 = _SocketWithName(("::1", 8000, 0, 0))

    target = server._format_running_target(socket_with_ipv6)  # type: ignore[arg-type]

    assert target == "http://[::1]:8000"


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

    assert server._enter_request_slot() is True
    assert server._enter_request_slot() is False
    server._leave_request_slot()
    assert server._enter_request_slot() is True
    server._leave_request_slot()


def test_request_slot_unlimited_is_always_available() -> None:
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=None)
    )

    assert server._enter_request_slot() is True
    server._leave_request_slot()


def test_is_concurrency_limit_exceeded_matches_uvicorn_semantics() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=2))
    server.server_state.connections = {object()}  # type: ignore[assignment]
    server.server_state.tasks = {object()}  # type: ignore[assignment]
    assert server._is_concurrency_limit_exceeded() is False

    server.server_state.connections = {object(), object()}  # type: ignore[assignment]
    assert server._is_concurrency_limit_exceeded() is True


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


def test_validate_protocol_backends_rejects_missing_wsproto(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="wsproto"))

    def fake_find_spec(name: str):
        if name == "wsproto":
            return None
        return object()

    monkeypatch.setattr(server_module, "find_spec", fake_find_spec)
    with pytest.raises(RuntimeError, match="wsproto"):
        server._validate_protocol_backends()


def test_validate_protocol_backends_rejects_missing_websockets(monkeypatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="websockets"))

    def fake_find_spec(name: str):
        if name == "websockets":
            return None
        return object()

    monkeypatch.setattr(server_module, "find_spec", fake_find_spec)
    with pytest.raises(RuntimeError, match="websockets"):
        server._validate_protocol_backends()


def test_validate_protocol_backends_allows_auto_when_no_ws_backends(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "_module_available", lambda name: False)
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="auto"))
    monkeypatch.setattr(server_module, "find_spec", lambda name: None)
    server._validate_protocol_backends()


def test_build_ssl_context_returns_none_without_certfile() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    assert server._build_ssl_context() is None


def test_build_ssl_context_configures_certificate_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeContext:
        def __init__(self, version: int) -> None:
            captured["version"] = version

        def load_cert_chain(self, certfile: str, keyfile: str | None, password) -> None:
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
    assert callable(captured["password"])
    assert captured["password"]() == "secret"
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


def test_handle_connection_uses_custom_ws_protocol_class(monkeypatch) -> None:
    class DummyWSProtocol(asyncio.Protocol):
        pass

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="websockets"))
    server._resolved_app = _resolved_app()
    server.config.ws_protocol_class = DummyWSProtocol
    writer = DummyWriter()
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

    custom_ws_calls: list[str] = []
    regular_ws_calls: list[str] = []

    async def fake_run_custom_ws_protocol(self, *, request, reader, writer):
        custom_ws_calls.append(request.target)

    async def fake_handle_websocket(*args, **kwargs):
        regular_ws_calls.append("ws")

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(server_module, "is_websocket_upgrade", lambda req: True)
    monkeypatch.setattr(PalfreyServer, "_run_custom_ws_protocol", fake_run_custom_ws_protocol)
    monkeypatch.setattr(server_module, "handle_websocket", fake_handle_websocket)

    asyncio.run(server._handle_connection(object(), writer))

    assert custom_ws_calls == ["/ws"]
    assert regular_ws_calls == []
    assert writer.closed is True


def test_handle_connection_returns_400_for_upgrade_when_ws_backend_disabled(
    monkeypatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="none"))
    server._resolved_app = _resolved_app()
    writer = DummyWriter()
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

    called: list[str] = []

    async def fake_handle_websocket(*args, **kwargs):
        called.append("ws")

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(server_module, "is_websocket_upgrade", lambda req: True)
    monkeypatch.setattr(server_module, "handle_websocket", fake_handle_websocket)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"400 Bad Request" in payload
    assert called == []
    assert writer.closed is True


def test_handle_connection_sends_100_continue_and_respects_max_requests(
    monkeypatch,
) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=1,
        timeout_keep_alive=1,
    )
    server = PalfreyServer(config)

    async def app(scope, receive, send):
        message = await receive()
        assert message == {"type": "http.request", "body": b"hello", "more_body": False}
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    server._resolved_app = ResolvedApp(app=app, interface="asgi3")
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

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(server_module, "should_keep_alive", lambda request, response: False)

    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"100 Continue" in payload
    assert b"200 OK" in payload
    assert server._shutdown_event.is_set() is True


def test_handle_connection_returns_503_when_concurrency_limit_reached(
    monkeypatch,
) -> None:
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


def test_run_custom_ws_protocol_forwards_handshake_and_stream_bytes() -> None:
    events: list[tuple[str, bytes | None]] = []
    transport = object()

    class DummyWSProtocol(asyncio.Protocol):
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def connection_made(self, received_transport) -> None:
            assert received_transport is transport

        def data_received(self, data: bytes) -> None:
            events.append(("data", data))

        def eof_received(self):
            events.append(("eof", None))
            return None

        def connection_lost(self, exc: Exception | None) -> None:
            events.append(("lost", None))

    class DummyProtocolWriter(DummyWriter):
        def __init__(self) -> None:
            super().__init__()
            self.transport = transport

        def is_closing(self) -> bool:
            return False

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", ws="websockets"))
    server.config.ws_protocol_class = DummyWSProtocol
    writer = DummyProtocolWriter()
    request = HTTPRequest(
        method="GET",
        target="/ws?x=1",
        http_version="HTTP/1.1",
        headers=[("upgrade", "websocket"), ("connection", "Upgrade")],
        body=b"",
    )

    async def scenario() -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(b"frame-bytes")
        reader.feed_eof()
        await server._run_custom_ws_protocol(request=request, reader=reader, writer=writer)

    asyncio.run(scenario())

    assert events[0][0] == "data"
    assert events[0][1] is not None
    assert b"GET /ws?x=1 HTTP/1.1\r\n" in events[0][1]
    assert b"upgrade: websocket\r\n" in events[0][1].lower()
    assert events[1] == ("data", b"frame-bytes")
    assert events[2] == ("eof", None)
    assert events[3] == ("lost", None)


def test_handle_connection_returns_503_when_connection_count_reaches_limit(
    monkeypatch,
) -> None:
    # Set limit to 1
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=1))
    server._resolved_app = _resolved_app()

    # Seed the connections so the limit is ALREADY reached
    server.server_state.connections.add(object())

    writer = DummyWriter()
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )

    # Mock the reader to return our request
    async def fake_read_request(reader, **kwargs):
        return request

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)

    # Run the connection handler
    asyncio.run(server._handle_connection(object(), writer))

    payload = b"".join(writer.writes)
    assert b"503 Service Unavailable" in payload


def test_request_slot_zero_limit_always_blocks() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=0)
    server = PalfreyServer(config)

    assert server._enter_request_slot() is False
