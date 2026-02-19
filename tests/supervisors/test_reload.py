"""Reload supervisor helper tests."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import palfrey.supervisors.reload as reload_module
from palfrey.config import PalfreyConfig
from palfrey.supervisors.reload import ReloadSupervisor, build_reload_argv


def test_build_reload_argv_uses_current_process_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["-m", "palfrey", "tests.fixtures.apps:http_app"])
    argv = build_reload_argv()
    assert argv[0] == sys.executable
    assert argv[1:] == ["-m", "palfrey", "tests.fixtures.apps:http_app"]


def test_reload_supervisor_default_include_patterns() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    assert supervisor._include_patterns() == ["*.py"]


def test_reload_supervisor_uses_custom_patterns() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_includes=["*.txt"],
        reload_excludes=["*.tmp"],
    )
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    assert supervisor._include_patterns() == ["*.txt"]
    assert supervisor._exclude_patterns() == ["*.tmp"]


def test_changed_paths_detects_file_updates(tmp_path: Path) -> None:
    watched = tmp_path / "app.py"
    watched.write_text("print('v1')\n", encoding="utf-8")

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(tmp_path)],
    )
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])

    first_scan = supervisor._changed_paths()
    assert first_scan == []

    time.sleep(0.02)
    watched.write_text("print('v2')\n", encoding="utf-8")

    second_scan = supervisor._changed_paths()
    assert watched in second_scan


def test_changed_paths_respects_include_and_exclude(tmp_path: Path) -> None:
    include_file = tmp_path / "service.py"
    exclude_file = tmp_path / "ignored.py"
    include_file.write_text("v1", encoding="utf-8")
    exclude_file.write_text("v1", encoding="utf-8")

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(tmp_path)],
        reload_includes=["*.py"],
        reload_excludes=["ignored.py"],
    )
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    supervisor._changed_paths()

    time.sleep(0.02)
    include_file.write_text("v2", encoding="utf-8")
    exclude_file.write_text("v2", encoding="utf-8")

    changed = supervisor._changed_paths()
    assert include_file in changed
    assert exclude_file not in changed


def test_watch_roots_defaults_to_current_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=False, reload_dirs=[])
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: Path("/tmp")))
    assert supervisor._watch_roots() == [Path("/tmp")]


def test_watch_roots_uses_configured_paths(tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(one), str(two)],
    )
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    assert supervisor._watch_roots() == [one.resolve(), two.resolve()]


def test_spawn_sets_reload_child_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    captured: dict[str, object] = {}

    class FakeProcess:
        def poll(self) -> int | None:
            return None

    def fake_popen(argv: list[str], env: dict[str, str]):
        captured["argv"] = argv
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(reload_module.subprocess, "Popen", fake_popen)

    supervisor._spawn()
    assert captured["argv"] == ["python", "-m", "palfrey"]
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PALFREY_RELOAD_CHILD"] == "1"
    assert supervisor._process is not None


def test_terminate_kills_process_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])

    class FakeProcess:
        def __init__(self) -> None:
            self.signals: list[int] = []
            self.killed = False
            self.wait_calls = 0

        def poll(self) -> int | None:
            return None

        def send_signal(self, signum: int) -> None:
            self.signals.append(signum)

        def wait(self, timeout: float | None = None) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd="x", timeout=10)

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()
    supervisor._process = process  # type: ignore[assignment]

    supervisor._terminate()
    assert process.signals == [signal.SIGTERM]
    assert process.killed is True


def test_restart_terminates_then_spawns(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    calls: list[str] = []

    monkeypatch.setattr(ReloadSupervisor, "_terminate", lambda self: calls.append("terminate"))
    monkeypatch.setattr(ReloadSupervisor, "_spawn", lambda self: calls.append("spawn"))

    supervisor._restart()
    assert calls == ["terminate", "spawn"]


def test_restart_clears_tracked_mtimes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    tracked = tmp_path / "tracked.py"
    supervisor._mtimes[tracked] = 1.0

    monkeypatch.setattr(ReloadSupervisor, "_terminate", lambda self: None)
    monkeypatch.setattr(ReloadSupervisor, "_spawn", lambda self: None)

    supervisor._restart()
    assert supervisor._mtimes == {}


def test_run_restarts_when_changed_paths_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True, reload_delay=0)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    calls: list[str] = []

    class FakeProcess:
        def poll(self) -> int | None:
            return None

    def fake_spawn(self: ReloadSupervisor) -> None:
        calls.append("spawn")
        self._process = FakeProcess()  # type: ignore[assignment]

    def fake_changed(self: ReloadSupervisor) -> list[Path]:
        return [Path("changed.py")]

    def fake_restart(self: ReloadSupervisor) -> None:
        calls.append("restart")
        self._stop = True

    monkeypatch.setattr(reload_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(ReloadSupervisor, "_spawn", fake_spawn)
    monkeypatch.setattr(ReloadSupervisor, "_changed_paths", fake_changed)
    monkeypatch.setattr(ReloadSupervisor, "_restart", fake_restart)
    monkeypatch.setattr(ReloadSupervisor, "_terminate", lambda self: calls.append("terminate"))
    monkeypatch.setattr(reload_module.time, "sleep", lambda _: None)

    supervisor.run()
    assert calls == ["spawn", "restart", "terminate"]


def test_run_respawns_if_child_process_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True, reload_delay=0)
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    spawn_count = 0
    calls: list[str] = []

    class ExitedProcess:
        def poll(self) -> int | None:
            return 1

    class RunningProcess:
        def poll(self) -> int | None:
            return None

    def fake_spawn(self: ReloadSupervisor) -> None:
        nonlocal spawn_count
        spawn_count += 1
        calls.append("spawn")
        if spawn_count == 1:
            self._process = ExitedProcess()  # type: ignore[assignment]
        else:
            self._process = RunningProcess()  # type: ignore[assignment]
            self._stop = True

    monkeypatch.setattr(reload_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(ReloadSupervisor, "_spawn", fake_spawn)
    monkeypatch.setattr(ReloadSupervisor, "_changed_paths", lambda self: [])
    monkeypatch.setattr(ReloadSupervisor, "_terminate", lambda self: calls.append("terminate"))
    monkeypatch.setattr(reload_module.time, "sleep", lambda _: None)

    supervisor.run()
    assert calls == ["spawn", "spawn", "terminate"]
