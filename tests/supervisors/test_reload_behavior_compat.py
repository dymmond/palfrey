from __future__ import annotations

import signal
import time
from pathlib import Path

from palfrey.config import PalfreyConfig
from palfrey.supervisors.reload import ReloadSupervisor


def _supervisor(tmp_path: Path, **kwargs) -> ReloadSupervisor:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(tmp_path)],
        **kwargs,
    )
    return ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])


def test_on_signal_sets_stop_flag(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    assert supervisor._stop is False
    supervisor._on_signal(signal.SIGTERM, None)
    assert supervisor._stop is True


def test_changed_paths_ignores_non_matching_includes(tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("v1", encoding="utf-8")
    supervisor = _supervisor(tmp_path, reload_includes=["*.py"])
    supervisor._changed_paths()
    time.sleep(0.02)
    text_file.write_text("v2", encoding="utf-8")
    assert supervisor._changed_paths() == []


def test_changed_paths_supports_nested_glob_patterns(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    file = package / "app.py"
    file.write_text("v1", encoding="utf-8")
    supervisor = _supervisor(tmp_path, reload_includes=["pkg/*.py"])
    supervisor._changed_paths()
    time.sleep(0.02)
    file.write_text("v2", encoding="utf-8")
    assert file in supervisor._changed_paths()


def test_changed_paths_handles_deleted_files_gracefully(tmp_path: Path) -> None:
    file = tmp_path / "app.py"
    file.write_text("v1", encoding="utf-8")
    supervisor = _supervisor(tmp_path)
    supervisor._changed_paths()
    file.unlink()
    assert supervisor._changed_paths() == []


def test_changed_paths_tracks_multiple_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    file_a = root_a / "one.py"
    file_b = root_b / "two.py"
    file_a.write_text("a1", encoding="utf-8")
    file_b.write_text("b1", encoding="utf-8")
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        reload=True,
        reload_dirs=[str(root_a), str(root_b)],
    )
    supervisor = ReloadSupervisor(config=config, argv=["python", "-m", "palfrey"])
    supervisor._changed_paths()
    time.sleep(0.02)
    file_a.write_text("a2", encoding="utf-8")
    file_b.write_text("b2", encoding="utf-8")
    changed = supervisor._changed_paths()
    assert file_a in changed
    assert file_b in changed


def test_terminate_noop_when_process_missing(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor._process = None
    supervisor._terminate()  # should not raise


def test_terminate_noop_when_process_already_exited(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)

    class ExitedProcess:
        def poll(self) -> int | None:
            return 0

    supervisor._process = ExitedProcess()  # type: ignore[assignment]
    supervisor._terminate()


def test_exclude_pattern_wins_over_include_pattern(tmp_path: Path) -> None:
    file = tmp_path / "ignored.py"
    file.write_text("v1", encoding="utf-8")
    supervisor = _supervisor(tmp_path, reload_includes=["*.py"], reload_excludes=["ignored.py"])
    supervisor._changed_paths()
    time.sleep(0.02)
    file.write_text("v2", encoding="utf-8")
    assert file not in supervisor._changed_paths()


def test_default_include_pattern_is_python_files(tmp_path: Path) -> None:
    py_file = tmp_path / "main.py"
    txt_file = tmp_path / "main.txt"
    py_file.write_text("py1", encoding="utf-8")
    txt_file.write_text("txt1", encoding="utf-8")
    supervisor = _supervisor(tmp_path)
    supervisor._changed_paths()
    time.sleep(0.02)
    py_file.write_text("py2", encoding="utf-8")
    txt_file.write_text("txt2", encoding="utf-8")
    changed = supervisor._changed_paths()
    assert py_file in changed
    assert txt_file not in changed
