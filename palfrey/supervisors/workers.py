"""Multi-process worker supervisor."""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import time
from dataclasses import dataclass, field

from palfrey.config import PalfreyConfig
from palfrey.logging_config import get_logger
from palfrey.server import PalfreyServer

logger = get_logger("palfrey.supervisors.workers")


def _worker_entry(config: PalfreyConfig) -> None:
    server = PalfreyServer(config)
    server.run()


@dataclass(slots=True)
class WorkerSupervisor:
    """Run and monitor multiple worker processes."""

    config: PalfreyConfig
    _workers: list[mp.Process] = field(default_factory=list)
    _stopping: bool = False

    def run(self) -> None:
        """Start worker processes and monitor worker lifecycle."""

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._spawn_initial_workers()
        try:
            while not self._stopping:
                self._reap_and_restart_workers()
                time.sleep(0.5)
        finally:
            self._stop_workers()

    def _spawn_initial_workers(self) -> None:
        for _ in range(self.config.workers_count):
            self._spawn_worker()

    def _spawn_worker(self) -> None:
        process = mp.Process(target=_worker_entry, args=(self.config,), daemon=False)
        process.start()
        self._workers.append(process)
        logger.info("Started worker pid=%s", process.pid)

    def _reap_and_restart_workers(self) -> None:
        alive_workers: list[mp.Process] = []
        for process in self._workers:
            if process.is_alive():
                alive_workers.append(process)
                continue
            process.join(timeout=0.1)
            if not self._stopping:
                logger.warning("Worker pid=%s exited", process.pid)

        self._workers = alive_workers
        while len(self._workers) < self.config.workers_count and not self._stopping:
            self._spawn_worker()

    def _stop_workers(self) -> None:
        for process in self._workers:
            if process.is_alive():
                os.kill(process.pid, signal.SIGINT)

        deadline = time.monotonic() + self.config.timeout_worker_healthcheck
        for process in self._workers:
            timeout = max(0.0, deadline - time.monotonic())
            process.join(timeout=timeout)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)

    def _handle_signal(self, signum: int, _frame) -> None:
        logger.info("Received signal %s; stopping worker supervisor", signum)
        self._stopping = True
