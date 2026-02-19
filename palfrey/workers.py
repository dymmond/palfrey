"""Gunicorn worker integration for running Palfrey as an ASGI worker class."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import signal
import sys
from typing import Any, cast

from palfrey.config import PalfreyConfig
from palfrey.loops import resolve_loop_setup
from palfrey.server import PalfreyServer

SIGQUIT_SIGNAL = getattr(signal, "SIGQUIT", getattr(signal, "SIGBREAK", signal.SIGTERM))
if not hasattr(signal, "SIGQUIT"):
    signal.SIGQUIT = SIGQUIT_SIGNAL  # type: ignore[attr-defined]

if not hasattr(signal, "siginterrupt"):

    def _siginterrupt(_sig: int, _flag: bool) -> None:
        return None

    signal.siginterrupt = _siginterrupt  # type: ignore[attr-defined]


def _load_gunicorn_runtime() -> tuple[type[Any], int | None]:
    """Load Gunicorn worker class and boot-error code if dependency is installed."""

    try:
        workers_module = importlib.import_module("gunicorn.workers.base")
        arbiter_module = importlib.import_module("gunicorn.arbiter")
    except Exception:  # noqa: BLE001 - dependency may be intentionally absent.
        return object, None

    worker_base = getattr(workers_module, "Worker", object)
    if not isinstance(worker_base, type):
        return object, None

    arbiter_class = getattr(arbiter_module, "Arbiter", None)
    boot_error_value: int | None = None
    if arbiter_class is not None:
        raw_boot_error = getattr(arbiter_class, "WORKER_BOOT_ERROR", None)
        if raw_boot_error is not None:
            with contextlib.suppress(TypeError, ValueError):
                boot_error_value = int(raw_boot_error)

    return cast(type[Any], worker_base), boot_error_value


_WORKER_BASE_CLASS, _WORKER_BOOT_ERROR = _load_gunicorn_runtime()


class _MissingGunicornWorker:
    """Placeholder worker class used when gunicorn is not installed."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "palfrey.workers requires the 'gunicorn' package. Install gunicorn to use this worker."
        )


if _WORKER_BASE_CLASS is not object:

    class PalfreyWorker(_WORKER_BASE_CLASS):
        """Gunicorn worker implementation compatible with Palfrey's ASGI server."""

        CONFIG_KWARGS: dict[str, Any] = {"loop": "auto", "http": "auto"}

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)

            error_logger = logging.getLogger("palfrey.error")
            error_logger.handlers = self.log.error_log.handlers
            error_logger.setLevel(self.log.error_log.level)
            error_logger.propagate = False

            server_logger = logging.getLogger("palfrey.server")
            server_logger.handlers = self.log.error_log.handlers
            server_logger.setLevel(self.log.error_log.level)
            server_logger.propagate = False

            access_logger = logging.getLogger("palfrey.access")
            access_logger.handlers = self.log.access_log.handlers
            access_logger.setLevel(self.log.access_log.level)
            access_logger.propagate = False

            config_kwargs: dict[str, Any] = {
                "app": None,
                "log_config": None,
                "timeout_keep_alive": self.cfg.keepalive,
                "timeout_notify": self.timeout,
                "callback_notify": self.callback_notify,
                "limit_max_requests": self.max_requests,
                "forwarded_allow_ips": self.cfg.forwarded_allow_ips,
            }

            if self.cfg.is_ssl:
                ssl_kwargs = {
                    "ssl_keyfile": self.cfg.ssl_options.get("keyfile"),
                    "ssl_certfile": self.cfg.ssl_options.get("certfile"),
                    "ssl_keyfile_password": self.cfg.ssl_options.get("password"),
                    "ssl_version": self.cfg.ssl_options.get("ssl_version"),
                    "ssl_cert_reqs": self.cfg.ssl_options.get("cert_reqs"),
                    "ssl_ca_certs": self.cfg.ssl_options.get("ca_certs"),
                    "ssl_ciphers": self.cfg.ssl_options.get("ciphers"),
                }
                config_kwargs.update(ssl_kwargs)

            backlog_setting = self.cfg.settings.get("backlog")
            if backlog_setting is not None and backlog_setting.value:
                config_kwargs["backlog"] = backlog_setting.value

            config_kwargs.update(self.CONFIG_KWARGS)
            self.config = PalfreyConfig(**config_kwargs)

        def init_signals(self) -> None:
            """Reset signal handling to keep Gunicorn worker exit semantics."""

            for sig in self.SIGNALS:
                signal.signal(sig, signal.SIG_DFL)

            signal.signal(signal.SIGUSR1, self.handle_usr1)
            if hasattr(signal, "siginterrupt"):
                signal.siginterrupt(signal.SIGUSR1, False)

        def _install_sigquit_handler(self) -> None:
            """Install SIGQUIT loop handler for graceful worker shutdown."""

            loop = asyncio.get_running_loop()
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(SIGQUIT_SIGNAL, self.handle_exit, SIGQUIT_SIGNAL, None)

        async def _serve(self) -> None:
            """Run Palfrey server with sockets provided by Gunicorn."""

            self.config.app = self.wsgi
            server = PalfreyServer(config=self.config)
            self._install_sigquit_handler()
            await server.serve(sockets=self.sockets)
            if not server.started:
                exit_code = _WORKER_BOOT_ERROR if _WORKER_BOOT_ERROR is not None else 1
                sys.exit(exit_code)

        def run(self) -> None:
            """Run worker main loop with configured event loop policy."""

            resolve_loop_setup(self.config.loop)()
            asyncio.run(self._serve())

        async def callback_notify(self) -> None:
            """Bridge Palfrey's notify callback into Gunicorn worker heartbeat."""

            self.notify()

    class PalfreyH11Worker(PalfreyWorker):
        """Gunicorn worker variant forcing ``asyncio`` loop + ``h11`` parser."""

        CONFIG_KWARGS = {"loop": "asyncio", "http": "h11"}

else:
    PalfreyWorker = _MissingGunicornWorker
    PalfreyH11Worker = _MissingGunicornWorker
