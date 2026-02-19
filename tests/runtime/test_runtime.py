from __future__ import annotations

import logging

import pytest

import palfrey.runtime as runtime_module
from palfrey.config import PalfreyConfig
from palfrey.runtime import _configure_loop, _run_config, run


def test_configure_loop_rejects_unsupported_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported loop mode"):
        _configure_loop("invalid")


def test_run_config_ignores_workers_when_reload_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeReloadSupervisor:
        def __init__(
            self,
            config: PalfreyConfig,
            argv: list[str],
            pass_fds: tuple[int, ...] = (),
        ) -> None:
            calls.append("init")
            calls.append(f"pass_fds:{len(pass_fds)}")

        def run(self) -> None:
            calls.append("run")

    monkeypatch.setattr(runtime_module, "ReloadSupervisor", FakeReloadSupervisor)
    monkeypatch.setattr(
        runtime_module,
        "build_reload_argv",
        lambda *, fd=None: ["python", "-m", "palfrey", "--fd", str(fd)],
    )
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(
        PalfreyConfig,
        "bind_socket",
        lambda self: type(
            "Sock",
            (),
            {
                "fileno": lambda self: 123,
                "close": lambda self: None,
                "set_inheritable": lambda *_: None,
            },
        )(),
    )
    monkeypatch.delenv("PALFREY_RELOAD_CHILD", raising=False)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True, workers=2)

    messages: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    runtime_logger = logging.getLogger("palfrey.runtime")
    capture_handler = _CaptureHandler()
    runtime_logger.addHandler(capture_handler)
    try:
        _run_config(config)
    finally:
        runtime_logger.removeHandler(capture_handler)

    assert calls == ["init", "pass_fds:1", "run"]
    assert any(
        '"workers" flag is ignored when reloading is enabled.' in message for message in messages
    )


def test_run_config_rejects_reload_for_non_import_app() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, reload=True)
    with pytest.raises(RuntimeError, match="enable 'reload' or 'workers'"):
        _run_config(config)


def test_run_config_rejects_workers_for_non_import_app() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, workers=2)
    with pytest.raises(RuntimeError, match="enable 'reload' or 'workers'"):
        _run_config(config)


def test_run_config_uses_reload_supervisor_for_parent_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeReloadSupervisor:
        def __init__(
            self,
            config: PalfreyConfig,
            argv: list[str],
            pass_fds: tuple[int, ...] = (),
        ) -> None:
            called.append(f"init:{argv[0]}")
            called.append(f"fds:{len(pass_fds)}")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "ReloadSupervisor", FakeReloadSupervisor)
    monkeypatch.setattr(
        runtime_module,
        "build_reload_argv",
        lambda *, fd=None: ["python", "-m", "palfrey", "--fd", str(fd)],
    )
    monkeypatch.setattr(
        runtime_module, "_configure_loop", lambda loop_mode: called.append(loop_mode)
    )
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: called.append("env"))
    monkeypatch.setattr(
        PalfreyConfig,
        "bind_socket",
        lambda self: type(
            "Sock",
            (),
            {"fileno": lambda self: 123, "close": lambda self: called.append("close")},
        )(),
    )
    monkeypatch.delenv("PALFREY_RELOAD_CHILD", raising=False)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    _run_config(config)

    assert called == ["env", "auto", "init:python", "fds:1", "run", "close"]


def test_run_config_runs_server_when_reload_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeServer:
        def __init__(self, config: PalfreyConfig) -> None:
            called.append(f"server:{config.app}")

        def run(self) -> None:
            called.append("server.run")

    monkeypatch.setattr(runtime_module, "PalfreyServer", FakeServer)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setenv("PALFREY_RELOAD_CHILD", "1")

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    _run_config(config)

    assert called == ["server:tests.fixtures.apps:http_app", "server.run"]


def test_run_config_uses_worker_supervisor_when_worker_count_above_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeWorkerSupervisor:
        def __init__(self, config: PalfreyConfig, sockets=None) -> None:
            called.append(f"workers:{config.workers_count}")
            called.append(f"sockets:{0 if sockets is None else len(sockets)}")

        def run(self) -> None:
            called.append("workers.run")

    monkeypatch.setattr(runtime_module, "WorkerSupervisor", FakeWorkerSupervisor)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(
        PalfreyConfig,
        "bind_socket",
        lambda self: type(
            "Sock",
            (),
            {"fileno": lambda self: 321, "close": lambda self: called.append("close")},
        )(),
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2)
    _run_config(config)

    assert called == ["workers:2", "sockets:1", "workers.run", "close"]


def test_run_builds_config_from_app_and_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []

    def fake_run_config(config: PalfreyConfig) -> None:
        captured.append(config)

    monkeypatch.setattr(runtime_module, "_run_config", fake_run_config)

    run("tests.fixtures.apps:http_app", host="0.0.0.0", port=9000)

    assert len(captured) == 1
    assert captured[0].host == "0.0.0.0"
    assert captured[0].port == 9000


def test_run_uses_existing_config_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[PalfreyConfig] = []

    def fake_run_config(config: PalfreyConfig) -> None:
        captured.append(config)

    monkeypatch.setattr(runtime_module, "_run_config", fake_run_config)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    run(config)

    assert captured == [config]
