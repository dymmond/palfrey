"""Extended tests for ``PalfreyServer.serve`` branch behavior."""

from __future__ import annotations

import asyncio
import signal

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.importer import ResolvedApp
from palfrey.server import PalfreyServer


class FakeSocket:
    def __init__(self, name: tuple[str, int]) -> None:
        self._name = name
        self.blocking: bool | None = None

    def getsockname(self) -> tuple[str, int]:
        return self._name

    def setblocking(self, value: bool) -> None:
        self.blocking = value


class FakeAsyncServer:
    def __init__(self, sockets: list[FakeSocket] | None = None) -> None:
        self.sockets = sockets or [FakeSocket(("127.0.0.1", 8000))]
        self.closed = False
        self.wait_closed_called = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_called = True


class FakeLoop:
    def __init__(self) -> None:
        self.signals: list[int] = []

    def add_signal_handler(self, sig: int, _callback) -> None:
        self.signals.append(sig)


class FakeLifespanManager:
    def __init__(self, app) -> None:
        self.app = app
        self.started = False
        self.stopped = False

    async def startup(self) -> None:
        self.started = True

    async def shutdown(self) -> None:
        self.stopped = True


async def _noop_app(scope, receive, send):
    return None


def _resolved() -> ResolvedApp:
    return ResolvedApp(app=_noop_app, interface="asgi3")


def test_serve_uses_host_port_start_server(monkeypatch) -> None:
    calls: dict[str, object] = {}
    fake_server = FakeAsyncServer([FakeSocket(("127.0.0.1", 8123))])

    async def fake_start_server(handler, **kwargs):
        calls.update(kwargs)
        return fake_server

    loop = FakeLoop()

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: loop)

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8000
    assert calls["reuse_port"] is False
    assert fake_server.closed is True
    assert fake_server.wait_closed_called is True


def test_serve_sets_reuse_port_true_with_multiple_workers(monkeypatch) -> None:
    calls: dict[str, object] = {}

    async def fake_start_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer()

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2, lifespan="off")
    )
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["reuse_port"] is True


def test_serve_uses_start_unix_server_when_uds_is_configured(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    async def fake_start_unix_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer([FakeSocket(("unix", 0))])

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_unix_server", fake_start_unix_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    uds_path = tmp_path / "palfrey.sock"
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", uds=str(uds_path), lifespan="off")
    )
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["path"] == str(uds_path)


def test_serve_uses_socket_from_fd_when_configured(monkeypatch) -> None:
    calls: dict[str, object] = {}
    fake_socket = FakeSocket(("127.0.0.1", 8888))

    async def fake_start_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer([fake_socket])

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.socket, "fromfd", lambda fd, fam, typ: fake_socket)
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", fd=3, lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["sock"] is fake_socket
    assert fake_socket.blocking is False


def test_serve_initializes_and_shutdowns_lifespan_when_enabled(monkeypatch) -> None:
    holder: dict[str, FakeLifespanManager] = {}

    def build_manager(app):
        manager = FakeLifespanManager(app)
        holder["manager"] = manager
        return manager

    async def fake_start_server(handler, **kwargs):
        return FakeAsyncServer()

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module, "LifespanManager", build_manager)
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="auto"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    manager = holder["manager"]
    assert manager.started is True
    assert manager.stopped is True


def test_serve_registers_sigint_and_sigterm_handlers(monkeypatch) -> None:
    loop = FakeLoop()

    async def fake_start_server(handler, **kwargs):
        return FakeAsyncServer()

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: loop)

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert signal.SIGINT in loop.signals
    assert signal.SIGTERM in loop.signals


def test_request_shutdown_sets_shutdown_event() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    assert server._shutdown_event.is_set() is False
    server.request_shutdown()
    assert server._shutdown_event.is_set() is True


def test_started_property_reflects_server_presence() -> None:
    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    assert server.started is False
    server._server = FakeAsyncServer()  # type: ignore[assignment]
    assert server.started is True


def test_serve_passes_ssl_context_to_start_server(monkeypatch) -> None:
    calls: dict[str, object] = {}

    async def fake_start_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer()

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.PalfreyServer, "_build_ssl_context", lambda self: object())
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["ssl"] is not None
