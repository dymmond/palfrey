"""Multi-process worker supervisor."""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from palfrey.config import PalfreyConfig
from palfrey.logging_config import get_logger
from palfrey.server import PalfreyServer

logger = get_logger("palfrey.supervisors.workers")

SIGNALS = {
    getattr(signal, f"SIG{name}"): name
    for name in ("INT", "TERM", "BREAK", "HUP", "TTIN", "TTOU")
    if hasattr(signal, f"SIG{name}")
}


def _worker_entry(config: PalfreyConfig) -> None:
    server = PalfreyServer(config)
    server.run()


class WorkerProcess:
    """Wrap ``multiprocessing.Process`` with ping/pong health checks."""

    def __init__(
        self,
        config: PalfreyConfig,
        target: Callable[[PalfreyConfig], None],
    ) -> None:
        self._target = target
        self._parent_conn, self._child_conn = mp.Pipe()
        self._process = mp.Process(target=self._run, args=(config,), daemon=False)

    def _run(self, config: PalfreyConfig) -> Any:  # pragma: no cover - executed in child process.
        threading.Thread(target=self._always_pong, daemon=True).start()
        return self._target(config)

    def ping(self, timeout: float = 5) -> bool:
        """Send ping to child worker and wait for pong."""

        try:
            self._parent_conn.send(b"ping")
        except (BrokenPipeError, EOFError, OSError):
            return False

        if self._parent_conn.poll(timeout):
            with contextlib.suppress(BrokenPipeError, EOFError, OSError):
                self._parent_conn.recv()
                return True
        return False

    def _pong(self) -> None:
        self._child_conn.recv()
        self._child_conn.send(b"pong")

    def _always_pong(self) -> None:
        while True:
            self._pong()

    def is_alive(self, timeout: float = 5) -> bool:
        """Return health status combining process liveness and ping response."""

        if not self._process.is_alive():
            return False
        return self.ping(timeout)

    def start(self) -> None:
        self._process.start()

    @property
    def started(self) -> bool:
        """Return whether wrapped process object recorded a start marker."""

        return bool(getattr(self._process, "started", False))

    @property
    def args(self) -> tuple[Any, ...] | None:
        """Expose process args for testability and parity checks."""

        process_args = getattr(self._process, "args", None)
        if process_args is None:
            return None
        return tuple(process_args)

    def terminate(self) -> None:
        if self._process.exitcode is None and self.pid is not None:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):  # pragma: no cover
                os.kill(self.pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(self.pid, signal.SIGTERM)
            logger.info("Terminated child process [%s]", self.pid)
        self._close_pipes()

    def kill(self) -> None:
        self._process.kill()

    def join(self, timeout: float | None = None) -> None:
        self._process.join(timeout=timeout)

    @property
    def pid(self) -> int | None:
        return self._process.pid

    def _close_pipes(self) -> None:
        with contextlib.suppress(OSError):
            self._parent_conn.close()
        with contextlib.suppress(OSError):
            self._child_conn.close()


@dataclass(slots=True)
class WorkerSupervisor:
    """Run and monitor multiple worker processes."""

    config: PalfreyConfig
    _workers: list[WorkerProcess] = field(default_factory=list)
    _stopping: bool = False
    _signal_queue: list[int] = field(default_factory=list)
    _workers_num: int = 0
    _worker_target: Callable[[PalfreyConfig], None] = _worker_entry

    def __post_init__(self) -> None:
        self._workers_num = self.config.workers_count

    def run(self) -> None:
        """Start worker processes and monitor worker lifecycle."""

        for sig in SIGNALS:
            signal.signal(sig, self._capture_signal)

        self._spawn_initial_workers()
        try:
            while not self._stopping:
                self._handle_signals()
                self._reap_and_restart_workers()
                time.sleep(0.5)
        finally:
            self._stop_workers()

    def _capture_signal(self, signum: int, _frame: Any) -> None:
        self._signal_queue.append(signum)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """Backward-compatible signal entrypoint for existing callers/tests."""

        self._signal_queue.append(signum)
        self._handle_signals()

    def _handle_signals(self) -> None:
        while self._signal_queue:
            sig = self._signal_queue.pop(0)
            signal_name = SIGNALS.get(sig)
            if signal_name is None:
                continue
            handler = getattr(self, f"_handle_{signal_name.lower()}", None)
            if handler is not None:
                handler()

    def _handle_int(self) -> None:
        logger.info("Received SIGINT, stopping worker supervisor")
        self._stopping = True

    def _handle_term(self) -> None:
        logger.info("Received SIGTERM, stopping worker supervisor")
        self._stopping = True

    def _handle_break(self) -> None:  # pragma: no cover - windows only
        logger.info("Received SIGBREAK, stopping worker supervisor")
        self._stopping = True

    def _handle_hup(self) -> None:
        logger.info("Received SIGHUP, restarting worker processes")
        self._restart_workers()

    def _handle_ttin(self) -> None:
        logger.info("Received SIGTTIN, increasing worker process count")
        self._workers_num += 1
        self._spawn_worker()

    def _handle_ttou(self) -> None:
        logger.info("Received SIGTTOU, decreasing worker process count")
        if self._workers_num <= 1:
            logger.info("Already at one worker process; refusing to scale down further")
            return
        self._workers_num -= 1
        process = self._workers.pop()
        process.terminate()
        process.join(timeout=1.0)

    def _spawn_initial_workers(self) -> None:
        for _ in range(self._workers_num):
            self._spawn_worker()

    def _spawn_worker(self) -> None:
        process = WorkerProcess(self.config, target=self._worker_target)
        process.start()
        self._workers.append(process)
        logger.info("Started worker pid=%s", process.pid)

    def _reap_and_restart_workers(self) -> None:
        alive_workers: list[WorkerProcess] = []
        for process in self._workers:
            if self._is_process_alive(process):
                alive_workers.append(process)
                continue
            process.kill()
            process.join(timeout=0.1)
            if self._stopping:
                continue
            logger.warning("Worker pid=%s exited", process.pid)
        self._workers = alive_workers

        while len(self._workers) < self._workers_num and not self._stopping:
            self._spawn_worker()
        while len(self._workers) > self._workers_num and self._workers:
            process = self._workers.pop()
            self._terminate_process(process)
            process.join(timeout=1.0)

    @staticmethod
    def _is_process_alive(process: Any, timeout: float = 5.0) -> bool:
        try:
            return bool(process.is_alive(timeout=timeout))
        except TypeError:
            return bool(process.is_alive())

    def _restart_workers(self) -> None:
        for index, process in enumerate(list(self._workers)):
            self._terminate_process(process)
            process.join(timeout=1.0)
            replacement = WorkerProcess(self.config, target=self._worker_target)
            replacement.start()
            self._workers[index] = replacement

    def _stop_workers(self) -> None:
        for process in self._workers:
            self._terminate_process(process)

        deadline = time.monotonic() + self.config.timeout_worker_healthcheck
        for process in self._workers:
            timeout = max(0.0, deadline - time.monotonic())
            process.join(timeout=timeout)
            if self._is_process_alive(process, timeout=0.0):
                process.kill()
                process.join(timeout=2)

    def _terminate_process(self, process: Any) -> None:
        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            terminate()
            return

        pid = getattr(process, "pid", None)
        if pid is not None and self._is_process_alive(process, timeout=0.0):
            os.kill(pid, signal.SIGTERM)
