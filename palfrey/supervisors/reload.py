"""File-change reload supervisor."""

from __future__ import annotations

import fnmatch
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from palfrey.config import PalfreyConfig
from palfrey.logging_config import get_logger

logger = get_logger("palfrey.supervisors.reload")
DEFAULT_RELOAD_INCLUDES = ["*.py"]
DEFAULT_RELOAD_EXCLUDES = [".*", ".py[cod]", ".sw.*", "~*"]


@dataclass(slots=True)
class ReloadSupervisor:
    """Run server subprocess and restart it when watched files change."""

    config: PalfreyConfig
    argv: list[str]
    _process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None
    _stop: bool = False
    _mtimes: dict[Path, float] = field(default_factory=dict)

    def run(self) -> None:
        """Start the reloader loop and manage child process restarts."""

        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

        self._spawn()

        try:
            while not self._stop:
                changed = self._changed_paths()
                if changed:
                    logger.info(
                        "Reload triggered by changes: %s",
                        ", ".join(str(path) for path in changed),
                    )
                    self._restart()
                if self._process and self._process.poll() is not None:
                    logger.warning("Child process exited; restarting")
                    self._spawn()
                time.sleep(self.config.reload_delay)
        finally:
            self._terminate()

    def _spawn(self) -> None:
        env = os.environ.copy()
        env["PALFREY_RELOAD_CHILD"] = "1"
        self._process = subprocess.Popen(self.argv, env=env)

    def _restart(self) -> None:
        self._terminate()
        self._spawn()

    def _terminate(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.send_signal(signal.SIGINT)
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

    def _on_signal(self, signum: int, _frame) -> None:
        logger.info("Received signal %s; stopping reloader", signum)
        self._stop = True

    def _watch_roots(self) -> list[Path]:
        if self.config.reload_dirs:
            return [Path(path).resolve() for path in self.config.reload_dirs]
        return [Path.cwd()]

    def _include_patterns(self) -> list[str]:
        if self.config.reload_includes:
            return self.config.reload_includes
        return DEFAULT_RELOAD_INCLUDES

    def _exclude_patterns(self) -> list[str]:
        if self.config.reload_excludes:
            return self.config.reload_excludes
        return DEFAULT_RELOAD_EXCLUDES

    def _changed_paths(self) -> list[Path]:
        include_patterns = self._include_patterns()
        exclude_patterns = self._exclude_patterns()
        changed: list[Path] = []

        for root in self._watch_roots():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                relative = str(path.relative_to(root))
                filename = path.name
                absolute = str(path)
                include_match = any(
                    fnmatch.fnmatch(relative, pattern)
                    or fnmatch.fnmatch(filename, pattern)
                    or fnmatch.fnmatch(absolute, pattern)
                    for pattern in include_patterns
                )
                if not include_match:
                    continue
                exclude_match = any(
                    fnmatch.fnmatch(relative, pattern)
                    or fnmatch.fnmatch(filename, pattern)
                    or fnmatch.fnmatch(absolute, pattern)
                    for pattern in exclude_patterns
                )
                if exclude_match:
                    continue

                try:
                    mtime = path.stat().st_mtime
                except FileNotFoundError:
                    continue

                previous = self._mtimes.get(path)
                self._mtimes[path] = mtime
                if previous is not None and mtime > previous:
                    changed.append(path)

        return changed


def build_reload_argv() -> list[str]:
    """Build argv used to respawn the current Palfrey CLI command."""

    return [sys.executable, *sys.argv]
