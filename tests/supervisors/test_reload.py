"""Reload supervisor helper tests."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

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
