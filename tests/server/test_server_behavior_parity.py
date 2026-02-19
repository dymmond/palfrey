"""Additional server behavior tests aligned with Uvicorn server expectations."""

from __future__ import annotations

import asyncio
import logging
import signal

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


class FakeAsyncServer:
    def __init__(self) -> None:
        self.closed = False
        self.wait_closed_called = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_called = True


class FakeLifespan:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeConnection:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeTask:
    def __init__(self) -> None:
        self.cancelled = False
        self.message: str | None = None

    def cancel(self, msg: str | None = None) -> None:
        self.cancelled = True
        self.message = msg


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


def test_on_tick_populates_cached_default_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["x-extra: one"])
    )
    monkeypatch.setattr(server_module.time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        server_module,
        "formatdate",
        lambda _value, usegmt: "Tue, 01 Jan 2030 00:00:00 GMT",
    )

    should_exit = asyncio.run(server._on_tick(0))

    assert should_exit is False
    assert server.server_state.default_headers == [
        (b"date", b"Tue, 01 Jan 2030 00:00:00 GMT"),
        (b"server", b"palfrey"),
        (b"x-extra", b"one"),
    ]


def test_on_tick_triggers_callback_notify_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    notifications: list[str] = []

    async def callback_notify() -> None:
        notifications.append("called")

    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            callback_notify=callback_notify,
            timeout_notify=5,
        )
    )
    time_values = iter([1.0, 6.0, 8.0, 12.5])
    monkeypatch.setattr(server_module.time, "time", lambda: next(time_values))
    monkeypatch.setattr(
        server_module,
        "formatdate",
        lambda _value, usegmt: "Tue, 01 Jan 2030 00:00:00 GMT",
    )

    asyncio.run(server._on_tick(0))
    asyncio.run(server._on_tick(10))
    asyncio.run(server._on_tick(20))
    asyncio.run(server._on_tick(30))

    assert notifications == ["called", "called"]


def test_on_tick_returns_true_when_shutdown_requested() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server.request_shutdown()
    assert asyncio.run(server._on_tick(1)) is True


def test_on_tick_returns_true_when_max_requests_exceeded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        limit_max_requests=2,
        limit_max_requests_jitter=0,
    )
    server = PalfreyServer(config)
    server._max_requests_before_exit = 2
    server.server_state.total_requests = 2
    caplog.set_level(logging.INFO, logger="palfrey.server")

    should_exit = asyncio.run(server._on_tick(1))

    assert should_exit is True
    assert server._shutdown_event.is_set() is True
    assert "Maximum request limit of 2 exceeded" in caplog.text


def test_main_loop_runs_until_tick_requests_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    counters: list[int] = []

    async def fake_on_tick(self: PalfreyServer, counter: int) -> bool:
        counters.append(counter)
        return counter >= 1

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(PalfreyServer, "_on_tick", fake_on_tick)
    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)

    asyncio.run(server._main_loop())

    assert counters == [0, 1]


def test_shutdown_closes_server_and_runs_lifespan_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    fake_server = FakeAsyncServer()
    fake_lifespan = FakeLifespan()
    server._server = fake_server  # type: ignore[assignment]
    server._lifespan = fake_lifespan  # type: ignore[assignment]

    async def fake_wait_tasks_to_complete(self: PalfreyServer) -> None:
        return None

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(PalfreyServer, "_wait_tasks_to_complete", fake_wait_tasks_to_complete)
    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)

    asyncio.run(server._shutdown())

    assert fake_server.closed is True
    assert fake_server.wait_closed_called is True
    assert fake_lifespan.shutdown_calls == 1


def test_shutdown_requests_shutdown_on_all_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._server = FakeAsyncServer()  # type: ignore[assignment]
    connection_one = FakeConnection()
    connection_two = FakeConnection()
    server.server_state.connections = {connection_one, connection_two}  # type: ignore[assignment]

    async def fake_wait_tasks_to_complete(self: PalfreyServer) -> None:
        server.server_state.connections.clear()

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(PalfreyServer, "_wait_tasks_to_complete", fake_wait_tasks_to_complete)
    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)

    asyncio.run(server._shutdown())

    assert connection_one.shutdown_calls == 1
    assert connection_two.shutdown_calls == 1


def test_shutdown_cancels_tasks_when_graceful_timeout_expires(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    server = PalfreyServer(
        PalfreyConfig(
            app="tests.fixtures.apps:http_app",
            timeout_graceful_shutdown=0,
        )
    )
    server._server = FakeAsyncServer()  # type: ignore[assignment]
    task = FakeTask()
    server.server_state.tasks = {task}  # type: ignore[assignment]
    caplog.set_level(logging.ERROR, logger="palfrey.server")

    async def fake_wait_tasks_to_complete(self: PalfreyServer) -> None:
        return None

    async def fake_wait_for(awaitable, timeout):
        await awaitable
        raise asyncio.TimeoutError

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(PalfreyServer, "_wait_tasks_to_complete", fake_wait_tasks_to_complete)
    monkeypatch.setattr(server_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)

    asyncio.run(server._shutdown())

    assert task.cancelled is True
    assert task.message == "Task cancelled, timeout graceful shutdown exceeded"
    assert "timeout graceful shutdown exceeded" in caplog.text


def test_wait_tasks_to_complete_waits_for_connections_and_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server.server_state.connections = {object()}  # type: ignore[assignment]
    server.server_state.tasks = {object()}  # type: ignore[assignment]
    sleep_calls = {"count": 0}

    async def fake_sleep(_delay: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] == 1:
            server.server_state.connections.clear()
        elif sleep_calls["count"] == 2:
            server.server_state.tasks.clear()

    monkeypatch.setattr(server_module.asyncio, "sleep", fake_sleep)

    asyncio.run(server._wait_tasks_to_complete())

    assert sleep_calls["count"] == 2


def test_handle_exit_signal_sets_force_exit_on_second_sigint() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._handle_exit_signal(signal.SIGINT)
    assert server._shutdown_event.is_set() is True
    assert server._force_exit is False

    server._handle_exit_signal(signal.SIGINT)
    assert server._force_exit is True


def test_capture_signals_restores_handlers_and_replays_in_lifo_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    current_handlers: dict[int, object] = {}
    original_handlers: dict[int, object] = {}
    raised_signals: list[int] = []

    def fake_signal(sig: int, handler: object) -> object:
        previous = current_handlers.get(sig, f"orig-{sig}")
        if sig not in original_handlers:
            original_handlers[sig] = previous
        current_handlers[sig] = handler
        return previous

    monkeypatch.setattr(server_module.signal, "signal", fake_signal)
    monkeypatch.setattr(server_module.signal, "raise_signal", lambda sig: raised_signals.append(sig))

    with server.capture_signals():
        server.handle_exit(int(signal.SIGTERM), None)
        server.handle_exit(int(signal.SIGINT), None)

    assert raised_signals == [int(signal.SIGINT), int(signal.SIGTERM)]
    for sig, original_handler in original_handlers.items():
        assert current_handlers[sig] == original_handler
    assert server._shutdown_event.is_set() is True
    assert server._force_exit is True


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

    async def fake_run_http_asgi(app, scope, body, **kwargs):
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

    async def fake_run_http_asgi(app, scope, body, **kwargs):
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


def test_handle_http_request_uses_cached_default_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
    server._resolved_app = _resolved_http_app()
    server.server_state.default_headers = [
        (b"server", b"edge-cache"),
        (b"date", b"Tue, 01 Jan 2030 00:00:00 GMT"),
    ]
    request = HTTPRequest(
        method="GET",
        target="/cached",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )

    async def fake_run_http_asgi(app, scope, body, **kwargs):
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    monkeypatch.setattr(server_module, "run_http_asgi", fake_run_http_asgi)
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

    header_map = {name.lower(): value for name, value in response.headers}
    assert header_map[b"server"] == b"edge-cache"
    assert header_map[b"date"] == b"Tue, 01 Jan 2030 00:00:00 GMT"


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
