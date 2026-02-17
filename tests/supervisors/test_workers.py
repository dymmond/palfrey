"""Worker supervisor logic tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from palfrey.config import PalfreyConfig
from palfrey.supervisors.workers import WorkerSupervisor


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

    def fake_spawn_worker() -> None:
        process = FakeProcess(pid=100 + len(spawned), alive=True)
        spawned.append(process)
        supervisor._workers.append(process)  # type: ignore[arg-type]

    monkeypatch.setattr(supervisor, "_spawn_worker", fake_spawn_worker)

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
