"""Gunicorn worker parity tests for ``palfrey.workers``."""

from __future__ import annotations

import asyncio
import importlib
import logging
import signal
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _restore_palfrey_loggers():
    logger_names = ("palfrey.error", "palfrey.server", "palfrey.access")
    snapshot: dict[str, tuple[list[logging.Handler], int, bool]] = {}
    for name in logger_names:
        logger = logging.getLogger(name)
        snapshot[name] = (list(logger.handlers), logger.level, logger.propagate)
    yield
    for name in logger_names:
        logger = logging.getLogger(name)
        handlers, level, propagate = snapshot[name]
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def _clear_workers_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "palfrey.workers", raising=False)
    monkeypatch.delitem(sys.modules, "gunicorn", raising=False)
    monkeypatch.delitem(sys.modules, "gunicorn.arbiter", raising=False)
    monkeypatch.delitem(sys.modules, "gunicorn.workers", raising=False)
    monkeypatch.delitem(sys.modules, "gunicorn.workers.base", raising=False)


def _install_fake_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeArbiter:
        WORKER_BOOT_ERROR = 3

    class FakeWorker:
        SIGNALS = (signal.SIGINT, signal.SIGTERM)

        def __init__(self, *args, **kwargs) -> None:
            error_handler = logging.NullHandler()
            access_handler = logging.NullHandler()
            self.log = types.SimpleNamespace(
                error_log=types.SimpleNamespace(handlers=[error_handler], level=20),
                access_log=types.SimpleNamespace(handlers=[access_handler], level=20),
            )
            self.cfg = types.SimpleNamespace(
                keepalive=11,
                forwarded_allow_ips="*",
                is_ssl=False,
                ssl_options={},
                settings={"backlog": types.SimpleNamespace(value=64)},
            )
            self.timeout = 9
            self.max_requests = 123
            self.sockets = [object()]
            self.wsgi = "tests.fixtures.apps:http_app"
            self.notified = 0

        def notify(self) -> None:
            self.notified += 1

        def handle_usr1(self, *_args) -> None:
            return None

        def handle_exit(self, *_args) -> None:
            return None

    gunicorn_module = types.ModuleType("gunicorn")
    arbiter_module = types.ModuleType("gunicorn.arbiter")
    workers_pkg = types.ModuleType("gunicorn.workers")
    workers_base_module = types.ModuleType("gunicorn.workers.base")
    arbiter_module.Arbiter = FakeArbiter
    workers_base_module.Worker = FakeWorker

    monkeypatch.setitem(sys.modules, "gunicorn", gunicorn_module)
    monkeypatch.setitem(sys.modules, "gunicorn.arbiter", arbiter_module)
    monkeypatch.setitem(sys.modules, "gunicorn.workers", workers_pkg)
    monkeypatch.setitem(sys.modules, "gunicorn.workers.base", workers_base_module)


def _load_workers_module(monkeypatch: pytest.MonkeyPatch, *, with_gunicorn: bool):
    _clear_workers_modules(monkeypatch)
    if with_gunicorn:
        _install_fake_gunicorn(monkeypatch)
    return importlib.import_module("palfrey.workers")


def test_workers_module_requires_gunicorn_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=False)
    with pytest.raises(RuntimeError, match="requires the 'gunicorn' package"):
        workers_module.PalfreyWorker()


def test_palfrey_worker_builds_config_from_gunicorn_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=True)
    worker = workers_module.PalfreyWorker()

    assert worker.config.timeout_keep_alive == 11
    assert worker.config.timeout_notify == 9
    assert worker.config.limit_max_requests == 123
    assert worker.config.forwarded_allow_ips == "*"
    assert worker.config.backlog == 64
    assert worker.config.loop == "auto"
    assert worker.config.http == "auto"

    h11_worker = workers_module.PalfreyH11Worker()
    assert h11_worker.config.loop == "asyncio"
    assert h11_worker.config.http == "h11"


def test_palfrey_worker_init_signals_resets_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=True)
    worker = workers_module.PalfreyWorker()
    signal_calls: list[tuple[int, object]] = []
    siginterrupt_calls: list[tuple[int, bool]] = []

    monkeypatch.setattr(
        workers_module.signal,
        "signal",
        lambda sig, handler: signal_calls.append((int(sig), handler)),
    )
    monkeypatch.setattr(
        workers_module.signal,
        "siginterrupt",
        lambda sig, flag: siginterrupt_calls.append((int(sig), flag)),
    )

    worker.init_signals()

    assert (int(signal.SIGINT), workers_module.signal.SIG_DFL) in signal_calls
    assert (int(signal.SIGTERM), workers_module.signal.SIG_DFL) in signal_calls
    assert (int(signal.SIGUSR1), worker.handle_usr1) in signal_calls
    assert siginterrupt_calls == [(int(signal.SIGUSR1), False)]


def test_palfrey_worker_serve_uses_passed_sockets_and_boot_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=True)
    worker = workers_module.PalfreyWorker()
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, config) -> None:
            self.config = config
            self.started = False

        async def serve(self, sockets=None) -> None:
            captured["sockets"] = sockets

    monkeypatch.setattr(workers_module, "PalfreyServer", FakeServer)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(worker._serve())

    assert exc_info.value.code == 3
    assert captured["sockets"] == worker.sockets
    assert worker.config.app == worker.wsgi


def test_palfrey_worker_run_configures_loop_and_executes_coroutine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=True)
    worker = workers_module.PalfreyWorker()
    observed: dict[str, object] = {}

    async def fake_serve() -> None:
        observed["served"] = True

    def fake_resolve_loop_setup(mode: str):
        def setup() -> None:
            observed["loop_mode"] = mode

        return setup

    def fake_asyncio_run(coro):
        observed["ran"] = True
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(worker, "_serve", fake_serve)
    monkeypatch.setattr(workers_module, "resolve_loop_setup", fake_resolve_loop_setup)
    monkeypatch.setattr(workers_module.asyncio, "run", fake_asyncio_run)

    worker.run()

    assert observed["loop_mode"] == worker.config.loop
    assert observed["served"] is True
    assert observed["ran"] is True


def test_palfrey_worker_callback_notify_bridges_to_notify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_module = _load_workers_module(monkeypatch, with_gunicorn=True)
    worker = workers_module.PalfreyWorker()

    asyncio.run(worker.callback_notify())
    assert worker.notified == 1
