from __future__ import annotations

import pytest

import palfrey.runtime as runtime_module
from palfrey.config import PalfreyConfig
from palfrey.runtime import _configure_loop, _run_config


def test_configure_loop_invokes_registered_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        runtime_module,
        "resolve_loop_setup",
        lambda _: lambda: called.append("custom"),
    )
    _configure_loop("custom")
    assert called == ["custom"]


def test_run_config_starts_server_for_single_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeServer:
        def __init__(self, config: PalfreyConfig) -> None:
            called.append("init")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "PalfreyServer", FakeServer)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: called.append("env"))
    monkeypatch.setattr(
        runtime_module, "_configure_loop", lambda mode: called.append(f"loop:{mode}")
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=1)
    _run_config(config)
    assert called == ["env", "loop:auto", "init", "run"]


def test_run_config_reload_non_string_app_is_rejected() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, reload=True)
    with pytest.raises(RuntimeError, match="enable 'reload' or 'workers'"):
        _run_config(config)


def test_run_config_workers_non_string_app_is_rejected() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, workers=2)
    with pytest.raises(RuntimeError, match="enable 'reload' or 'workers'"):
        _run_config(config)


def test_run_config_uses_reload_supervisor_for_reload_parent(
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
            called.append("init")
            called.append(f"pass_fds:{len(pass_fds)}")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "ReloadSupervisor", FakeReloadSupervisor)
    monkeypatch.setattr(
        runtime_module,
        "build_reload_argv",
        lambda *, fd=None: ["python", "-m", "palfrey", "--fd", str(fd)],
    )
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(
        PalfreyConfig,
        "bind_socket",
        lambda self: type(
            "Sock",
            (),
            {"fileno": lambda self: 55, "close": lambda self: None},
        )(),
    )
    monkeypatch.delenv("PALFREY_RELOAD_CHILD", raising=False)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    _run_config(config)
    assert called == ["init", "pass_fds:1", "run"]


def test_run_config_uses_worker_supervisor_for_multi_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeWorkerSupervisor:
        def __init__(self, config: PalfreyConfig, sockets=None) -> None:
            called.append("init")
            called.append(f"sockets:{0 if sockets is None else len(sockets)}")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "WorkerSupervisor", FakeWorkerSupervisor)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(
        PalfreyConfig,
        "bind_socket",
        lambda self: type(
            "Sock",
            (),
            {"fileno": lambda self: 77, "close": lambda self: None},
        )(),
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2)
    _run_config(config)
    assert called == ["init", "sockets:1", "run"]


def test_run_config_removes_uds_socket_on_exit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    socket_path = tmp_path / "palfrey.sock"
    removed: list[str] = []

    class FakeServer:
        def __init__(self, config: PalfreyConfig) -> None:
            self.config = config

        def run(self) -> None:
            return None

    monkeypatch.setattr(runtime_module, "PalfreyServer", FakeServer)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: path == str(socket_path))
    monkeypatch.setattr(runtime_module.os, "remove", lambda path: removed.append(path))

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", uds=str(socket_path))
    _run_config(config)

    assert removed == [str(socket_path)]
