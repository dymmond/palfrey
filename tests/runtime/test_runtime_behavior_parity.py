"""Additional runtime orchestration tests."""

from __future__ import annotations

import pytest

import palfrey.runtime as runtime_module
from palfrey.config import PalfreyConfig
from palfrey.runtime import _configure_loop, _run_config


def test_configure_loop_invokes_registered_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setitem(runtime_module.LOOP_SETUPS, "custom", lambda: called.append("custom"))
    _configure_loop("custom")
    assert called == ["custom"]


def test_run_config_starts_server_for_single_worker(monkeypatch: pytest.MonkeyPatch) -> None:
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
    with pytest.raises(
        RuntimeError, match="Reload mode requires the application to be an import string"
    ):
        _run_config(config)


def test_run_config_workers_non_string_app_is_rejected() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, workers=2)
    with pytest.raises(
        RuntimeError, match="Worker mode requires the application to be an import string"
    ):
        _run_config(config)


def test_run_config_uses_reload_supervisor_for_reload_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeReloadSupervisor:
        def __init__(self, config: PalfreyConfig, argv: list[str]) -> None:
            called.append("init")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "ReloadSupervisor", FakeReloadSupervisor)
    monkeypatch.setattr(runtime_module, "build_reload_argv", lambda: ["python", "-m", "palfrey"])
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)
    monkeypatch.delenv("PALFREY_RELOAD_CHILD", raising=False)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    _run_config(config)
    assert called == ["init", "run"]


def test_run_config_uses_worker_supervisor_for_multi_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeWorkerSupervisor:
        def __init__(self, config: PalfreyConfig) -> None:
            called.append("init")

        def run(self) -> None:
            called.append("run")

    monkeypatch.setattr(runtime_module, "WorkerSupervisor", FakeWorkerSupervisor)
    monkeypatch.setattr(runtime_module, "load_env_file", lambda _: None)
    monkeypatch.setattr(runtime_module, "_configure_loop", lambda _: None)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2)
    _run_config(config)
    assert called == ["init", "run"]
