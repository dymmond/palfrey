from __future__ import annotations

import fnmatch
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palfrey.config import PalfreyConfig

from palfrey.logging_config import get_logger

logger = get_logger("palfrey.supervisors.reload")

# Default file extensions and names to monitor for changes
DEFAULT_RELOAD_INCLUDES = ["*.py"]

# Default patterns to ignore, such as hidden files and compiled bytecode
DEFAULT_RELOAD_EXCLUDES = [".*", ".py[cod]", ".sw.*", "~*"]


@dataclass(slots=True)
class ReloadSupervisor:
    """
    Orchestrates the lifecycle of a child server process with automatic restarts on file changes.

    This supervisor monitors specified directories for modifications to files matching
    inclusion patterns while ignoring those in exclusion lists. When a change is detected,
    the child process is terminated and respawned.

    Attributes:
        config (PalfreyConfig): Configuration object containing reload delay and path settings.
        argv (list[str]): The command-line arguments used to spawn the child process.
        pass_fds (tuple[int, ...]): A collection of file descriptors to inherit in the child.
    """

    config: PalfreyConfig
    argv: list[str]
    pass_fds: tuple[int, ...] = ()
    _process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None
    _stop: bool = False
    _mtimes: dict[Path, float] = field(default_factory=dict)

    def run(self) -> None:
        """
        Enter the main reloader loop.

        Registers signal handlers for graceful shutdown and continuously polls for file
        modifications. If a change is detected or the child exits unexpectedly, it
        triggers a process restart.
        """
        # Register handlers to ensure the supervisor and child stop together on Ctrl+C
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

                # Automatically recover if the child process dies for any reason
                if self._process and self._process.poll() is not None:
                    logger.warning("Child process exited; restarting")
                    self._spawn()

                # Throttling the loop to prevent high CPU usage during file scanning
                time.sleep(self.config.reload_delay)
        finally:
            self._terminate()

    def _spawn(self) -> None:
        """
        Spawn a new instance of the child process.
        """
        env = os.environ.copy()
        # Set an environment variable so the child knows it is managed by a reloader
        env["PALFREY_RELOAD_CHILD"] = "1"

        # pass_fds is not supported on Windows and will cause a ValueError if provided
        if self.pass_fds and os.name != "nt":
            self._process = subprocess.Popen(self.argv, env=env, pass_fds=self.pass_fds)
        else:
            self._process = subprocess.Popen(self.argv, env=env)

    def _restart(self) -> None:
        """
        Cleanly shut down the current child process and start a fresh one.
        """
        # Clear mtimes to ensure a clean state for the next scan cycle
        self._mtimes.clear()
        self._terminate()
        self._spawn()

    def _terminate(self) -> None:
        """
        Gracefully terminate the child process, falling back to a hard kill if necessary.
        """
        if self._process is None:
            return

        if self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                # Give the child 10 seconds to shut down gracefully
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Child process failed to terminate; killing")
                self._process.kill()
                self._process.wait(timeout=5)

    def _on_signal(self, signum: int, _frame) -> None:
        """
        Capture termination signals to break the reloader loop.
        """
        logger.info("Received signal %s; stopping reloader", signum)
        self._stop = True

    def _watch_roots(self) -> list[Path]:
        """
        Determine which base directories should be recursively watched.

        Returns:
            list[Path]: A list of resolved directory paths.
        """
        if self.config.reload_dirs:
            return [Path(path).resolve() for path in self.config.reload_dirs]
        return [Path.cwd()]

    def _include_patterns(self) -> list[str]:
        """
        Retrieve patterns used to identify files that should trigger a reload.
        """
        if self.config.reload_includes:
            return self.config.reload_includes
        return DEFAULT_RELOAD_INCLUDES

    def _exclude_patterns(self) -> list[str]:
        """
        Retrieve patterns used to identify files that should be ignored.
        """
        if self.config.reload_excludes:
            return self.config.reload_excludes
        return DEFAULT_RELOAD_EXCLUDES

    def _changed_paths(self) -> list[Path]:
        """
        Scan the filesystem for files that have been modified since the last check.

        Returns:
            list[Path]: A list of paths that triggered a reload event.
        """
        include_patterns = self._include_patterns()
        exclude_patterns = self._exclude_patterns()
        changed: list[Path] = []

        for root in self._watch_roots():
            # rglob("*") performs a recursive walk through the directory tree
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                relative = str(path.relative_to(root))
                filename = path.name
                absolute = str(path)

                # Check if the file matches any inclusion pattern (relative, name, or absolute)
                include_match = any(
                    fnmatch.fnmatch(relative, pattern)
                    or fnmatch.fnmatch(filename, pattern)
                    or fnmatch.fnmatch(absolute, pattern)
                    for pattern in include_patterns
                )
                if not include_match:
                    continue

                # Check if the file matches any exclusion pattern
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
                    # File might have been deleted during the scan
                    continue

                previous = self._mtimes.get(path)
                self._mtimes[path] = mtime

                # If we have seen this file before and its mtime has increased, it changed
                if previous is not None and mtime > previous:
                    changed.append(path)

        return changed


def build_reload_argv(*, fd: int | None = None) -> list[str]:
    """
    Construct the argument list necessary to restart the current process.

    This identifies the current Python interpreter and the original script arguments
    to ensure the child process is an exact replica of the original execution.

    Args:
        fd (int | None, optional): An optional file descriptor to preserve across
            the restart (e.g., a shared socket). Defaults to None.

    Returns:
        list[str]: The command-line arguments for subprocess spawning.
    """
    argv = [sys.executable, *sys.argv]
    if fd is not None:
        argv.extend(["--fd", str(fd)])
    return argv
