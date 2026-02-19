from __future__ import annotations

import contextlib
import multiprocessing as mp
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from palfrey.config import PalfreyConfig
from palfrey.logging_config import get_logger
from palfrey.server import PalfreyServer

logger = get_logger("palfrey.supervisors.workers")

# Mapping of signal numbers to their string names for internal routing and logging.
SIGNALS = {
    getattr(signal, f"SIG{name}"): name
    for name in ("INT", "TERM", "BREAK", "HUP", "TTIN", "TTOU")
    if hasattr(signal, f"SIG{name}")
}


def _worker_entry(config: PalfreyConfig, sockets: list[socket.socket] | None = None) -> None:
    """
    The main entry point executed within a child worker process.

    This function instantiates the PalfreyServer and starts its execution loop
    using the provided configuration and shared sockets.

    Args:
        config (PalfreyConfig): The application configuration.
        sockets (list[socket.socket] | None, optional): Pre-bound sockets to listen on.
            Defaults to None.
    """
    server = PalfreyServer(config)
    server.run(sockets=sockets)


class WorkerProcess:
    """
    A high-level wrapper around a multiprocessing.Process with health monitoring.

    This class manages a single worker process and establishes a bi-directional
    pipe to perform heartbeat (ping/pong) checks, ensuring the process is not
    just alive but also responsive.
    """

    def __init__(
        self,
        config: PalfreyConfig,
        target: Callable[[PalfreyConfig, list[socket.socket] | None], None],
        *,
        sockets: list[socket.socket] | None = None,
    ) -> None:
        """
        Initialize the worker process container.

        Args:
            config (PalfreyConfig): The configuration to pass to the worker.
            target (Callable): The entry point function for the process.
            sockets (list[socket.socket] | None, optional): Sockets for the worker.
                Defaults to None.
        """
        self._target = target
        self._sockets = sockets
        # Pipe for inter-process communication (IPC) for health checks
        self._parent_conn, self._child_conn = mp.Pipe()
        self._process = mp.Process(target=self._run, args=(config, sockets), daemon=False)

    def _run(
        self,
        config: PalfreyConfig,
        sockets: list[socket.socket] | None,
    ) -> Any:
        """
        Internal wrapper for the target function, executed in the child process.

        Starts a background thread dedicated to responding to parent pings before
        invoking the primary server target.
        """
        # Daemon thread ensures health monitoring exists as long as the process does
        threading.Thread(target=self._always_pong, daemon=True).start()
        return self._target(config, sockets)

    def ping(self, timeout: float = 5) -> bool:
        """
        Perform a liveness check by sending a ping to the child process.

        Args:
            timeout (float, optional): Seconds to wait for a pong response.
                Defaults to 5.

        Returns:
            bool: True if the child responded with 'pong' within the timeout.
        """
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
        """
        Internal logic for the child process to receive a ping and send a pong.
        """
        self._child_conn.recv()
        self._child_conn.send(b"pong")

    def _always_pong(self) -> None:
        """
        Main loop for the child's heartbeat thread.
        """
        while True:
            self._pong()

    def is_alive(self, timeout: float = 5) -> bool:
        """
        Verify both process existence and application-level responsiveness.

        Args:
            timeout (float, optional): Heartbeat response timeout. Defaults to 5.

        Returns:
            bool: True if the process is running and responsive.
        """
        if not self._process.is_alive():
            return False
        return self.ping(timeout)

    def start(self) -> None:
        """
        Launch the underlying multiprocessing worker.
        """
        self._process.start()

    @property
    def started(self) -> bool:
        """
        Check if the process start() method has been called.
        """
        return bool(getattr(self._process, "started", False))

    @property
    def args(self) -> tuple[Any, ...] | None:
        """
        Access the arguments passed to the multiprocessing object.
        """
        process_args = getattr(self._process, "args", None)
        if process_args is None:
            return None
        return tuple(process_args)

    def terminate(self) -> None:
        """
        Gently request the child process to stop.

        Uses SIGTERM on POSIX and CTRL_BREAK_EVENT on Windows if available.
        """
        if self._process.exitcode is None and self.pid is not None:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                os.kill(self.pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(self.pid, signal.SIGTERM)
            logger.info("Terminated child process [%s]", self.pid)
        self._close_pipes()

    def kill(self) -> None:
        """
        Forcefully stop the child process.
        """
        self._process.kill()

    def join(self, timeout: float | None = None) -> None:
        """
        Wait for the child process to exit.
        """
        self._process.join(timeout=timeout)

    @property
    def pid(self) -> int | None:
        """
        The Process ID of the child worker.
        """
        return self._process.pid

    def _close_pipes(self) -> None:
        """
        Clean up IPC resources.
        """
        with contextlib.suppress(OSError):
            self._parent_conn.close()
        with contextlib.suppress(OSError):
            self._child_conn.close()


@dataclass(slots=True)
class WorkerSupervisor:
    """
    Manager for the worker process lifecycle, scaling, and signal handling.

    The supervisor ensures a fixed number of workers are running, re-spawns
    failed ones, and allows dynamic scaling via signals (SIGTTIN/SIGTTOU).
    """

    config: PalfreyConfig
    sockets: list[socket.socket] | None = None
    _workers: list[WorkerProcess] = field(default_factory=list)
    _stopping: bool = False
    _signal_queue: list[int] = field(default_factory=list)
    _workers_num: int = 0
    _worker_target: Callable[[PalfreyConfig, list[socket.socket] | None], None] = _worker_entry

    def __post_init__(self) -> None:
        """
        Initialize the target number of workers from the provided configuration.
        """
        self._workers_num = self.config.workers_count

    def run(self) -> None:
        """
        The main supervision loop.

        Registers signal handlers, spawns initial workers, and enters a
        monitoring loop until a termination signal is received.
        """
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
        """
        Callback to enqueue signals for synchronous processing in the main loop.
        """
        self._signal_queue.append(signum)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """
        Alternative entrypoint for signal handling, primarily for legacy/test use.
        """
        self._signal_queue.append(signum)
        self._handle_signals()

    def _handle_signals(self) -> None:
        """
        Drain the signal queue and dispatch to corresponding handler methods.
        """
        while self._signal_queue:
            sig = self._signal_queue.pop(0)
            signal_name = SIGNALS.get(sig)
            if signal_name is None:
                continue
            handler = getattr(self, f"_handle_{signal_name.lower()}", None)
            if handler is not None:
                handler()

    def _handle_int(self) -> None:
        """Triggered by SIGINT (Ctrl+C)."""
        logger.info("Received SIGINT, stopping worker supervisor")
        self._stopping = True

    def _handle_term(self) -> None:
        """Triggered by SIGTERM."""
        logger.info("Received SIGTERM, stopping worker supervisor")
        self._stopping = True

    def _handle_break(self) -> None:
        """Triggered by SIGBREAK (Windows)."""
        logger.info("Received SIGBREAK, stopping worker supervisor")
        self._stopping = True

    def _handle_hup(self) -> None:
        """Triggered by SIGHUP; performs a rolling restart of all workers."""
        logger.info("Received SIGHUP, restarting worker processes")
        self._restart_workers()

    def _handle_ttin(self) -> None:
        """Triggered by SIGTTIN; increases the worker count."""
        logger.info("Received SIGTTIN, increasing worker process count")
        self._workers_num += 1
        self._spawn_worker()

    def _handle_ttou(self) -> None:
        """Triggered by SIGTTOU; decreases the worker count down to a minimum of 1."""
        logger.info("Received SIGTTOU, decreasing worker process count")
        if self._workers_num <= 1:
            logger.info("Already at one worker process; refusing to scale down further")
            return
        self._workers_num -= 1
        process = self._workers.pop()
        process.terminate()
        process.join(timeout=1.0)

    def _spawn_initial_workers(self) -> None:
        """
        Bootstrap the pool of workers.
        """
        for _ in range(self._workers_num):
            self._spawn_worker()

    def _spawn_worker(self) -> None:
        """
        Create and start a new worker process.
        """
        process = WorkerProcess(self.config, target=self._worker_target, sockets=self.sockets)
        process.start()
        self._workers.append(process)
        logger.info("Started worker pid=%s", process.pid)

    def _reap_and_restart_workers(self) -> None:
        """
        Scan worker health, clean up dead processes, and maintain the target count.
        """
        alive_workers: list[WorkerProcess] = []
        for process in self._workers:
            if self._is_process_alive(process):
                alive_workers.append(process)
                continue

            # Process is dead or non-responsive
            process.kill()
            process.join(timeout=0.1)
            if self._stopping:
                continue
            logger.warning("Worker pid=%s exited", process.pid)

        self._workers = alive_workers

        # Ensure we have the correct number of workers based on current scaling settings
        while len(self._workers) < self._workers_num and not self._stopping:
            self._spawn_worker()
        while len(self._workers) > self._workers_num and self._workers:
            process = self._workers.pop()
            self._terminate_process(process)
            process.join(timeout=1.0)

    @staticmethod
    def _is_process_alive(process: Any, timeout: float = 5.0) -> bool:
        """
        Helper to check process liveness with signature compatibility.
        """
        try:
            return bool(process.is_alive(timeout=timeout))
        except TypeError:
            return bool(process.is_alive())

    def _restart_workers(self) -> None:
        """
        Force a termination and replacement of every worker in the pool.
        """
        for index, process in enumerate(list(self._workers)):
            self._terminate_process(process)
            process.join(timeout=1.0)
            replacement = WorkerProcess(
                self.config, target=self._worker_target, sockets=self.sockets
            )
            replacement.start()
            self._workers[index] = replacement

    def _stop_workers(self) -> None:
        """
        Initiate shutdown of all managed workers and wait for completion.
        """
        for process in self._workers:
            self._terminate_process(process)

        # Allow workers some time to shut down gracefully before forcing a kill
        deadline = time.monotonic() + self.config.timeout_worker_healthcheck
        for process in self._workers:
            timeout = max(0.0, deadline - time.monotonic())
            process.join(timeout=timeout)
            if self._is_process_alive(process, timeout=0.0):
                process.kill()
                process.join(timeout=2)

    def _terminate_process(self, process: Any) -> None:
        """
        Send a termination request to a worker, with fallbacks for raw PID killing.
        """
        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            terminate()
            return

        pid = getattr(process, "pid", None)
        if pid is not None and self._is_process_alive(process, timeout=0.0):
            os.kill(pid, signal.SIGTERM)
