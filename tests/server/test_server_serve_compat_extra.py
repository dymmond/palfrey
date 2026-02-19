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
        self.closed = False

    def getsockname(self) -> tuple[str, int]:
        return self._name

    def setblocking(self, value: bool) -> None:
        self.blocking = value

    def close(self) -> None:
        self.closed = True


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

    async def create_server(self, *_args, **_kwargs):
        raise NotImplementedError


class FakeLifespanManager:
    def __init__(self, app, lifespan_mode: str = "auto") -> None:
        self.app = app
        self.lifespan_mode = lifespan_mode
        self.started = False
        self.stopped = False
        self.should_exit = False

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


def test_serve_uses_prebound_sockets_when_provided(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    prebound = [FakeSocket(("127.0.0.1", 9000)), FakeSocket(("127.0.0.1", 9001))]

    async def fake_start_server(handler, **kwargs):
        calls.append(kwargs)
        return FakeAsyncServer([kwargs["sock"]])

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve(sockets=prebound))

    assert [call["sock"] for call in calls] == prebound
    assert all(sock.closed for sock in prebound)


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


def test_serve_reapplies_existing_uds_permissions(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    async def fake_start_unix_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer([FakeSocket(("unix", 0))])

    class FakeStat:
        st_mode = 0o640
        st_size = 0
        st_mtime = 0.0

    chmod_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_unix_server", fake_start_unix_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(server_module.os.path, "exists", lambda path: True)
    monkeypatch.setattr(server_module.os, "stat", lambda *_args, **_kwargs: FakeStat())
    monkeypatch.setattr(
        server_module.os, "chmod", lambda path, mode: chmod_calls.append((path, mode))
    )

    uds_path = tmp_path / "palfrey.sock"
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", uds=str(uds_path), lifespan="off")
    )
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert chmod_calls == [(str(uds_path), 0o640)]


def test_serve_sets_default_uds_permissions_when_socket_missing(monkeypatch, tmp_path) -> None:
    async def fake_start_unix_server(handler, **kwargs):
        return FakeAsyncServer([FakeSocket(("unix", 0))])

    chmod_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(server_module.asyncio, "start_unix_server", fake_start_unix_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(server_module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        server_module.os, "chmod", lambda path, mode: chmod_calls.append((path, mode))
    )

    uds_path = tmp_path / "palfrey.sock"
    server = PalfreyServer(
        PalfreyConfig(app="tests.fixtures.apps:http_app", uds=str(uds_path), lifespan="off")
    )
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert chmod_calls == [(str(uds_path), 0o666)]


def test_serve_uses_socket_from_fd_when_configured(monkeypatch) -> None:
    calls: dict[str, object] = {}
    fromfd_calls: list[tuple[int, int, int]] = []
    fake_socket = FakeSocket(("127.0.0.1", 8888))

    async def fake_start_server(handler, **kwargs):
        calls.update(kwargs)
        return FakeAsyncServer([fake_socket])

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module, "resolve_application", lambda config: _resolved())
    monkeypatch.setattr(
        server_module.socket,
        "fromfd",
        lambda fd, fam, typ: fromfd_calls.append((fd, fam, typ)) or fake_socket,
    )
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", fd=3, lifespan="off"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["sock"] is fake_socket
    assert fake_socket.blocking is False
    assert fromfd_calls == [(3, server_module.socket.AF_UNIX, server_module.socket.SOCK_STREAM)]


def test_serve_initializes_and_shutdowns_lifespan_when_enabled(monkeypatch) -> None:
    holder: dict[str, FakeLifespanManager] = {}

    def build_manager(app, lifespan_mode: str = "auto"):
        manager = FakeLifespanManager(app, lifespan_mode=lifespan_mode)
        holder["manager"] = manager
        return manager

    async def fake_start_server(handler, **kwargs):
        return FakeAsyncServer()

    def fake_load(self: PalfreyConfig) -> None:
        resolved = _resolved()
        self.loaded_app = resolved.app
        self.interface = resolved.interface
        self.lifespan_class = build_manager
        self.loaded = True

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(PalfreyConfig, "load", fake_load)
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="auto"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    manager = holder["manager"]
    assert manager.started is True
    assert manager.stopped is True


def test_serve_uses_custom_http_protocol_class_factory(monkeypatch) -> None:
    created: dict[str, object] = {}
    create_server_calls: list[dict[str, object]] = []

    class RecordingHTTPProtocol(asyncio.Protocol):
        def __init__(
            self,
            *,
            config,
            server_state,
            app_state,
            _loop=None,
        ) -> None:
            created["config"] = config
            created["server_state"] = server_state
            created["app_state"] = app_state
            created["loop"] = _loop

    class LoopWithCreateServer:
        def __init__(self) -> None:
            self.signals: list[int] = []

        def add_signal_handler(self, sig: int, _callback) -> None:
            self.signals.append(sig)

        async def create_server(self, protocol_factory, **kwargs):
            create_server_calls.append(kwargs)
            created["protocol"] = protocol_factory(self)
            return FakeAsyncServer([FakeSocket(("127.0.0.1", 9444))])

    loop = LoopWithCreateServer()

    async def should_not_call_start_server(*_args, **_kwargs):
        raise AssertionError("asyncio.start_server should not be used for custom protocol mode")

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(server_module.asyncio, "start_server", should_not_call_start_server)

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http=RecordingHTTPProtocol,
        lifespan="off",
    )
    server = PalfreyServer(config)
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert isinstance(created.get("protocol"), RecordingHTTPProtocol)
    assert created["config"] is config
    assert created["server_state"] is server.server_state
    assert created["app_state"] == {}
    assert created["loop"] is loop
    assert create_server_calls
    assert create_server_calls[0]["host"] == "127.0.0.1"
    assert create_server_calls[0]["port"] == 8000


def test_serve_auto_mode_continues_when_lifespan_is_unsupported(monkeypatch) -> None:
    calls = {"start_server": 0}

    class UnsupportedManager(FakeLifespanManager):
        async def startup(self) -> None:
            self.should_exit = self.lifespan_mode == "on"

    async def fake_start_server(handler, **kwargs):
        calls["start_server"] += 1
        return FakeAsyncServer()

    def fake_load(self: PalfreyConfig) -> None:
        resolved = _resolved()
        self.loaded_app = resolved.app
        self.interface = resolved.interface
        self.lifespan_class = UnsupportedManager
        self.loaded = True

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(PalfreyConfig, "load", fake_load)
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="auto"))
    server._shutdown_event.set()
    asyncio.run(server.serve())

    assert calls["start_server"] == 1
    assert server.started is True


def test_serve_on_mode_stops_when_lifespan_is_unsupported(monkeypatch) -> None:
    calls = {"start_server": 0}

    class UnsupportedManager(FakeLifespanManager):
        async def startup(self) -> None:
            self.should_exit = self.lifespan_mode == "on"

    async def fake_start_server(handler, **kwargs):
        calls["start_server"] += 1
        return FakeAsyncServer()

    def fake_load(self: PalfreyConfig) -> None:
        resolved = _resolved()
        self.loaded_app = resolved.app
        self.interface = resolved.interface
        self.lifespan_class = UnsupportedManager
        self.loaded = True

    monkeypatch.setattr(server_module, "configure_logging", lambda config: None)
    monkeypatch.setattr(PalfreyConfig, "load", fake_load)
    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    monkeypatch.setattr(server_module.asyncio, "get_running_loop", lambda: FakeLoop())

    server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app", lifespan="on"))
    asyncio.run(server.serve())

    assert calls["start_server"] == 0
    assert server.started is False


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
