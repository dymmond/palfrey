"""Worker supervisor logic tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import palfrey.supervisors.workers as workers_module
from palfrey.config import PalfreyConfig
from palfrey.supervisors.workers import WorkerSupervisor, _worker_entry


@dataclass
class FakeProcess:
    pid: int
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


def test_reap_and_restart_maintains_worker_count(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=2)
    supervisor = WorkerSupervisor(config=config)

    p1 = FakeProcess(pid=1, alive=True)
    p2 = FakeProcess(pid=2, alive=False)
    supervisor._workers = [p1, p2]  # type: ignore[assignment]

    spawned: list[FakeProcess] = []

    def fake_spawn_worker(self: WorkerSupervisor) -> None:
        process = FakeProcess(pid=100 + len(spawned), alive=True)
        spawned.append(process)
        self._workers.append(process)  # type: ignore[arg-type]

    monkeypatch.setattr(WorkerSupervisor, "_spawn_worker", fake_spawn_worker)

    supervisor._reap_and_restart_workers()

    assert len(supervisor._workers) == 2
    assert p1 in supervisor._workers
    assert p2 not in supervisor._workers
    assert spawned


def test_stop_workers_signals_and_kills_stuck_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        workers=1,
        timeout_worker_healthcheck=0,
    )
    supervisor = WorkerSupervisor(config=config)

    alive_process = FakeProcess(pid=11, alive=True)
    supervisor._workers = [alive_process]  # type: ignore[assignment]

    sent_signals: list[tuple[int, int]] = []

    def fake_kill(pid: int, signum: int) -> None:
        sent_signals.append((pid, signum))

    monkeypatch.setattr("os.kill", fake_kill)

    supervisor._stop_workers()

    assert sent_signals
    assert alive_process.joined
    assert alive_process.killed


def test_spawn_initial_workers_uses_effective_worker_count(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=3)
    supervisor = WorkerSupervisor(config=config)

    calls: list[int] = []

    def fake_spawn(self: WorkerSupervisor) -> None:
        calls.append(len(self._workers))

    monkeypatch.setattr(WorkerSupervisor, "_spawn_worker", fake_spawn)

    supervisor._spawn_initial_workers()
    assert len(calls) == 3


def test_spawn_worker_creates_process_and_starts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", workers=1)
    supervisor = WorkerSupervisor(config=config)

    class FakeMPProcess:
        def __init__(self, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.pid = 321
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            return None

        def kill(self) -> None:
            return None

    monkeypatch.setattr(workers_module.mp, "Process", FakeMPProcess)

    supervisor._spawn_worker()

    assert len(supervisor._workers) == 1
    spawned = supervisor._workers[0]
    assert spawned.pid == 321
    assert spawned.started is True
    assert spawned.args == (config,)


def test_worker_entry_bootstraps_server(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    calls: list[str] = []

    class FakeServer:
        def __init__(self, server_config: PalfreyConfig) -> None:
            assert server_config is config
            calls.append("init")

        def run(self) -> None:
            calls.append("run")

    monkeypatch.setattr(workers_module, "PalfreyServer", FakeServer)

    _worker_entry(config)
    assert calls == ["init", "run"]


def test_handle_signal_sets_stopping_flag() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    supervisor = WorkerSupervisor(config=config)
    assert supervisor._stopping is False
    supervisor._handle_signal(15, None)
    assert supervisor._stopping is True


def test_run_loops_until_stopping_and_always_stops_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    supervisor = WorkerSupervisor(config=config)
    calls: list[str] = []

    monkeypatch.setattr(workers_module.signal, "signal", lambda *args, **kwargs: None)

    def fake_spawn_initial(self: WorkerSupervisor) -> None:
        calls.append("spawn")

    def fake_reap(self: WorkerSupervisor) -> None:
        calls.append("reap")
        self._stopping = True

    def fake_stop(self: WorkerSupervisor) -> None:
        calls.append("stop")

    monkeypatch.setattr(WorkerSupervisor, "_spawn_initial_workers", fake_spawn_initial)
    monkeypatch.setattr(WorkerSupervisor, "_reap_and_restart_workers", fake_reap)
    monkeypatch.setattr(WorkerSupervisor, "_stop_workers", fake_stop)

    supervisor.run()
    assert calls == ["spawn", "reap", "stop"]
