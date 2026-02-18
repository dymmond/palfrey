"""Additional worker supervisor behavior tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import palfrey.supervisors.workers as workers_module
from palfrey.config import PalfreyConfig
from palfrey.supervisors.workers import WorkerSupervisor


@dataclass
class FakeProcess:
    pid: int | None
    alive: bool = True
    joined: bool = False
    killed: bool = False

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.joined = True

    def kill(self) -> None:
        self.killed = True
        self.alive = False


def test_reap_does_not_restart_when_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2)
    supervisor = WorkerSupervisor(config=config)
    supervisor._stopping = True
    supervisor._workers = [FakeProcess(pid=1, alive=False)]  # type: ignore[assignment]
    called = {"spawn": 0}

    def fake_spawn(self: WorkerSupervisor) -> None:
        called["spawn"] += 1

    monkeypatch.setattr(WorkerSupervisor, "_spawn_worker", fake_spawn)
    supervisor._reap_and_restart_workers()
    assert called["spawn"] == 0


def test_reap_joins_dead_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=1)
    supervisor = WorkerSupervisor(config=config)
    dead = FakeProcess(pid=2, alive=False)
    supervisor._workers = [dead]  # type: ignore[assignment]

    def fake_spawn(self: WorkerSupervisor) -> None:
        self._stopping = True

    monkeypatch.setattr(WorkerSupervisor, "_spawn_worker", fake_spawn)
    supervisor._reap_and_restart_workers()
    assert dead.joined is True


def test_stop_workers_skips_process_without_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app", workers=1, timeout_worker_healthcheck=0
    )
    supervisor = WorkerSupervisor(config=config)
    process = FakeProcess(pid=None, alive=True)
    supervisor._workers = [process]  # type: ignore[assignment]
    calls: list[tuple[int, int]] = []

    monkeypatch.setattr("os.kill", lambda pid, signum: calls.append((pid, signum)))
    supervisor._stop_workers()
    assert calls == []


def test_stop_workers_joins_exited_processes_without_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app", workers=1, timeout_worker_healthcheck=1
    )
    supervisor = WorkerSupervisor(config=config)
    process = FakeProcess(pid=3, alive=False)
    supervisor._workers = [process]  # type: ignore[assignment]

    monkeypatch.setattr("os.kill", lambda pid, signum: None)
    supervisor._stop_workers()
    assert process.joined is True
    assert process.killed is False


def test_stop_workers_kills_stuck_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app", workers=1, timeout_worker_healthcheck=0
    )
    supervisor = WorkerSupervisor(config=config)
    process = FakeProcess(pid=4, alive=True)
    supervisor._workers = [process]  # type: ignore[assignment]
    monkeypatch.setattr("os.kill", lambda pid, signum: None)
    supervisor._stop_workers()
    assert process.killed is True


def test_run_registers_sigint_and_sigterm_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    supervisor = WorkerSupervisor(config=config)
    handlers: list[int] = []
    calls: list[str] = []

    def fake_signal(sig, handler):
        handlers.append(sig)

    monkeypatch.setattr(workers_module.signal, "signal", fake_signal)
    monkeypatch.setattr(
        WorkerSupervisor, "_spawn_initial_workers", lambda self: calls.append("spawn")
    )

    def fake_reap(self: WorkerSupervisor) -> None:
        calls.append("reap")
        self._stopping = True

    monkeypatch.setattr(WorkerSupervisor, "_reap_and_restart_workers", fake_reap)
    monkeypatch.setattr(WorkerSupervisor, "_stop_workers", lambda self: calls.append("stop"))
    supervisor.run()

    assert workers_module.signal.SIGINT in handlers
    assert workers_module.signal.SIGTERM in handlers
    assert calls == ["spawn", "reap", "stop"]


def test_spawn_initial_workers_with_single_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=1)
    supervisor = WorkerSupervisor(config=config)
    called = {"count": 0}

    def fake_spawn(self: WorkerSupervisor) -> None:
        called["count"] += 1

    monkeypatch.setattr(WorkerSupervisor, "_spawn_worker", fake_spawn)
    supervisor._spawn_initial_workers()
    assert called["count"] == 1
