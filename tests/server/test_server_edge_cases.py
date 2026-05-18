from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import cast

import pytest

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPRequest, HTTPResponse
from palfrey.server import ConnectionContext, PalfreyServer, _QueuedRequest


class _Writer:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False
        self._transport = object()

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def get_extra_info(self, name: str):
        if name == "peername":
            return ("127.0.0.1", 50001)
        if name == "sockname":
            return ("127.0.0.1", 8000)
        if name == "ssl_object":
            return None
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed

    @property
    def transport(self):
        return self._transport


def _resolved() -> SimpleNamespace:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    return SimpleNamespace(app=app, interface="asgi3")


def test_capture_signals_on_non_main_thread_skips_signal_handlers(
    monkeypatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    called = {"signal": 0}

    monkeypatch.setattr(
        server_module.signal,
        "signal",
        lambda *_args, **_kwargs: called.__setitem__("signal", called["signal"] + 1),
    )
    monkeypatch.setattr(server_module.threading, "current_thread", lambda: object())
    monkeypatch.setattr(server_module.threading, "main_thread", lambda: object())

    with server.capture_signals():
        pass

    assert called["signal"] == 0


@pytest.mark.asyncio
async def test_shutdown_ignores_noncallable_server_close_and_wait_closed(
    monkeypatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    server._servers = [SimpleNamespace(close=None, wait_closed=None)]  # type: ignore[list-item]

    async def fake_sleep(_delay: float) -> None:
        return None

    async def fake_wait_for(awaitable, timeout):
        await awaitable

    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(server_module.asyncio, "wait_for", fake_wait_for)

    await server._shutdown()
    assert server._servers == []


@pytest.mark.asyncio
async def test_handle_connection_returns_early_when_app_not_resolved() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    writer = _Writer()
    await server._handle_connection(asyncio.StreamReader(), cast(asyncio.StreamWriter, writer))
    assert writer.closed is False


@pytest.mark.asyncio
async def test_handle_connection_returns_503_when_request_slot_not_acquired(
    monkeypatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=1))
    server._resolved_app = _resolved()  # type: ignore[assignment]
    writer = _Writer()
    request = HTTPRequest(method="GET", target="/", http_version="HTTP/1.1", headers=[], body=b"")
    calls = {"count": 0}

    async def fake_read_request(_reader, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return request
        return None

    monkeypatch.setattr(server_module, "read_http_request", fake_read_request)
    monkeypatch.setattr(PalfreyServer, "_is_concurrency_limit_exceeded", lambda self: False)
    monkeypatch.setattr(PalfreyServer, "_enter_request_slot", lambda self: False)

    await server._handle_connection(asyncio.StreamReader(), cast(asyncio.StreamWriter, writer))

    payload = b"".join(writer.writes)
    assert b"503 Service Unavailable" in payload


@pytest.mark.asyncio
async def test_queue_with_backpressure_pauses_and_resumes_reader() -> None:
    class _Transport:
        def __init__(self) -> None:
            self.paused = 0
            self.resumed = 0

        def pause_reading(self) -> None:
            self.paused += 1

        def resume_reading(self) -> None:
            self.resumed += 1

    class _Reader:
        def __init__(self) -> None:
            self._transport = _Transport()

    class _Queue:
        def __init__(self) -> None:
            self.items: list[_QueuedRequest] = []

        def full(self) -> bool:
            return True

        async def put(self, item: _QueuedRequest) -> None:
            self.items.append(item)

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    reader = _Reader()
    queue = _Queue()

    await server._queue_with_backpressure(reader, queue, _QueuedRequest(request=None))  # type: ignore[arg-type]

    assert reader._transport.paused == 1
    assert reader._transport.resumed == 1


def test_pause_resume_reader_handle_missing_transport_and_transport_errors() -> None:
    class _ReaderNoTransport:
        _transport = None

    class _BrokenTransport:
        def pause_reading(self) -> None:
            raise RuntimeError("pause error")

        def resume_reading(self) -> None:
            raise RuntimeError("resume error")

    class _ReaderBroken:
        def __init__(self) -> None:
            self._transport = _BrokenTransport()

    PalfreyServer._pause_stream_reader(_ReaderNoTransport())  # type: ignore[arg-type]
    PalfreyServer._resume_stream_reader(_ReaderNoTransport())  # type: ignore[arg-type]
    PalfreyServer._pause_stream_reader(_ReaderBroken())  # type: ignore[arg-type]
    PalfreyServer._resume_stream_reader(_ReaderBroken())  # type: ignore[arg-type]


def test_log_running_messages_without_sockets_supports_uds_and_ipv6_host() -> None:
    messages: list[str] = []

    def capture_info(message: str, *args: object) -> None:
        messages.append(message % args if args else message)

    original_info = server_module.logger.info
    server_module.logger.info = capture_info  # type: ignore[assignment]

    uds_server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", uds="/tmp/palfrey.sock", lifespan="off")
    )
    try:
        uds_server._log_running_messages([])
        ipv6_server = PalfreyServer(
            PalfreyConfig(app="tests.fixtures.apps:http_app", host="::1", port=9100, lifespan="off")
        )
        ipv6_server._log_running_messages([])
    finally:
        server_module.logger.info = original_info  # type: ignore[assignment]

    assert any("unix socket /tmp/palfrey.sock" in message for message in messages)
    assert any("http://[::1]:9100" in message for message in messages)


def test_format_running_target_handles_error_and_non_tuple_values() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))

    class _SockRaises:
        def getsockname(self):
            raise OSError("boom")

    class _SockString:
        def getsockname(self):
            return "/tmp/p.sock"

    class _SockOdd:
        def getsockname(self):
            return 42

    assert server._format_running_target(_SockRaises()) == "<unknown>"  # type: ignore[arg-type]
    assert server._format_running_target(_SockString()) == "unix socket /tmp/p.sock"  # type: ignore[arg-type]
    assert server._format_running_target(_SockOdd()) == "42"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_handle_http_request_raises_when_application_unresolved() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    request = HTTPRequest(method="GET", target="/", http_version="HTTP/1.1", headers=[], body=b"")
    context = ConnectionContext(client=("127.0.0.1", 1), server=("127.0.0.1", 2), is_tls=False)

    with pytest.raises(RuntimeError, match="Application is not resolved"):
        await server._handle_http_request(request, context)


@pytest.mark.asyncio
async def test_http2_request_handler_handles_failures_and_shutdown_threshold(
    monkeypatch,
) -> None:
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", http="h2", limit_concurrency=1)
    )
    server._resolved_app = _resolved()  # type: ignore[assignment]
    server._max_requests_before_exit = 1
    captured: dict[str, HTTPResponse] = {}

    async def fake_serve_http2_connection(*, reader, writer, request_handler):
        request = HTTPRequest(
            method="GET",
            target="/h2",
            http_version="HTTP/2",
            headers=[("host", "localhost")],
            body=b"",
        )
        captured["response"] = await request_handler(request)

    async def failing_handle_http_request(self, request, context):
        raise RuntimeError("h2 boom")

    monkeypatch.setattr(server_module, "serve_http2_connection", fake_serve_http2_connection)
    monkeypatch.setattr(PalfreyServer, "_handle_http_request", failing_handle_http_request)

    await server._handle_http2_connection(
        reader=asyncio.StreamReader(),
        writer=cast(asyncio.StreamWriter, _Writer()),
        context=ConnectionContext(client=("127.0.0.1", 1), server=("127.0.0.1", 2), is_tls=False),
    )

    assert captured["response"].status == 500
    assert server._shutdown_event.is_set() is True


@pytest.mark.asyncio
async def test_http2_request_handler_returns_503_for_concurrency_guards(
    monkeypatch,
) -> None:
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", http="h2", limit_concurrency=1)
    )
    server._resolved_app = _resolved()  # type: ignore[assignment]

    responses: list[HTTPResponse] = []
    calls = {"count": 0}

    async def fake_serve_http2_connection(*, reader, writer, request_handler):
        request = HTTPRequest(
            method="GET",
            target="/h2",
            http_version="HTTP/2",
            headers=[("host", "localhost")],
            body=b"",
        )
        responses.append(await request_handler(request))

    def fake_is_exceeded(self) -> bool:
        return calls["count"] == 0

    def fake_enter_slot(self) -> bool:
        calls["count"] += 1
        return False

    monkeypatch.setattr(server_module, "serve_http2_connection", fake_serve_http2_connection)
    monkeypatch.setattr(PalfreyServer, "_is_concurrency_limit_exceeded", fake_is_exceeded)
    monkeypatch.setattr(PalfreyServer, "_enter_request_slot", fake_enter_slot)

    await server._handle_http2_connection(
        reader=asyncio.StreamReader(),
        writer=cast(asyncio.StreamWriter, _Writer()),
        context=ConnectionContext(client=("127.0.0.1", 1), server=("127.0.0.1", 2), is_tls=False),
    )
    await server._handle_http2_connection(
        reader=asyncio.StreamReader(),
        writer=cast(asyncio.StreamWriter, _Writer()),
        context=ConnectionContext(client=("127.0.0.1", 1), server=("127.0.0.1", 2), is_tls=False),
    )

    assert responses[0].status == 503
    assert responses[1].status == 503


@pytest.mark.asyncio
async def test_serve_http3_rejects_unsupported_modes() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", http="h3"))

    with pytest.raises(RuntimeError, match="pre-bound sockets"):
        await server._serve_http3(sockets=[])

    server.config.fd = 3
    with pytest.raises(RuntimeError, match="does not support --fd"):
        await server._serve_http3(sockets=None)

    server.config.fd = None
    server.config.uds = "/tmp/palfrey.sock"
    with pytest.raises(RuntimeError, match="does not support --uds"):
        await server._serve_http3(sockets=None)


@pytest.mark.asyncio
async def test_serve_http3_request_handler_covers_guard_and_error_paths(
    monkeypatch,
) -> None:
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            host="::1",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
            limit_concurrency=1,
        )
    )
    server._resolved_app = _resolved()  # type: ignore[assignment]

    captured: dict[str, object] = {}

    class _FakeAsyncServer:
        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    async def fake_create_http3_server(*, config, request_handler):
        captured["handler"] = request_handler
        return _FakeAsyncServer()

    async def fake_main_loop(self) -> None:
        return None

    async def fake_shutdown(self) -> None:
        return None

    async def fake_handle_http_request(self, request, context):
        raise RuntimeError("h3 boom")

    monkeypatch.setattr(server_module, "create_http3_server", fake_create_http3_server)
    monkeypatch.setattr(PalfreyServer, "_main_loop", fake_main_loop)
    monkeypatch.setattr(PalfreyServer, "_shutdown", fake_shutdown)
    monkeypatch.setattr(PalfreyServer, "_handle_http_request", fake_handle_http_request)

    await server._serve_http3(sockets=None)
    handler = cast(
        Callable[[HTTPRequest, tuple[str, int], tuple[str, int]], Awaitable[HTTPResponse]],
        captured["handler"],
    )

    request = HTTPRequest(method="GET", target="/", http_version="HTTP/3", headers=[], body=b"")

    server.server_state.connections = {object()}
    response = await handler(request, ("127.0.0.1", 1111), ("127.0.0.1", 8000))
    assert response.status == 503

    server.server_state.connections.clear()
    server._active_requests = 1
    response = await handler(request, ("127.0.0.1", 1111), ("127.0.0.1", 8000))
    assert response.status == 503

    server._active_requests = 0
    server._max_requests_before_exit = 1
    server.server_state.total_requests = 0
    response = await handler(request, ("127.0.0.1", 1111), ("127.0.0.1", 8000))
    assert response.status == 500
    assert server._shutdown_event.is_set() is True


def test_serve_http3_requires_resolved_app() -> None:
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            http="h3",
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem",
        )
    )
    with pytest.raises(RuntimeError, match="Application is not resolved"):
        asyncio.run(server._serve_http3(sockets=None))


def test_loop_backend_name_custom_class_string() -> None:
    class _Loop:
        __module__ = "custom.loop"

    assert PalfreyServer._loop_backend_name(_Loop()) == "custom.loop._Loop"  # type: ignore[arg-type]
