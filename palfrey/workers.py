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

# Define signal constants with cross-platform fallbacks for SIGQUIT and SIGUSR1.
# On Windows, these typically default to SIGBREAK or SIGTERM.
SIGQUIT_SIGNAL = getattr(signal, "SIGQUIT", getattr(signal, "SIGBREAK", signal.SIGTERM))
if not hasattr(signal, "SIGQUIT"):
    signal.SIGQUIT = SIGQUIT_SIGNAL

SIGUSR1_SIGNAL = getattr(signal, "SIGUSR1", getattr(signal, "SIGBREAK", signal.SIGTERM))
if not hasattr(signal, "SIGUSR1"):
    signal.SIGUSR1 = SIGUSR1_SIGNAL

if not hasattr(signal, "siginterrupt"):

    def _siginterrupt(_sig: int, _flag: bool) -> None:
        """
        No-op fallback for systems where signal.siginterrupt is unavailable.
        """
        return None

    signal.siginterrupt = _siginterrupt


def _load_gunicorn_runtime() -> tuple[type[Any], int | None]:
    """
    Attempt to dynamically load Gunicorn internal components to provide the base worker class.

    This function isolates Gunicorn imports to ensure Palfrey can still be imported
    without Gunicorn installed. It retrieves the base Worker class and the standard
    boot error exit code.

    Returns:
        tuple[type[typing.Any], int | None]: A tuple containing the Gunicorn Worker
            base class (or object if missing) and the WORKER_BOOT_ERROR code (or None).
    """
    try:
        workers_module = importlib.import_module("gunicorn.workers.base")
        arbiter_module = importlib.import_module("gunicorn.arbiter")
    except Exception:
        # Gunicorn is likely not installed or not in the path
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


# Global runtime loading of Gunicorn dependencies
_WORKER_BASE_CLASS, _WORKER_BOOT_ERROR = _load_gunicorn_runtime()


class _MissingGunicornWorker:
    """
    Stunt class used to provide a clear error message when Gunicorn is missing.

    If a user attempts to use the Palfrey worker without gunicorn installed,
    this class will raise a RuntimeError during instantiation.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Block instantiation with an informative error message.
        """
        raise RuntimeError(
            "palfrey.workers requires the 'gunicorn' package. Install gunicorn to use this worker."
        )


if _WORKER_BASE_CLASS is not object:

    class PalfreyWorker(_WORKER_BASE_CLASS):
        """
        Implementation of a Gunicorn worker class that runs the Palfrey ASGI server.

        This class bridges the Gunicorn worker lifecycle (signals, heartbeat/notify,
        and socket management) with the asynchronous Palfrey runtime. It extracts
        configuration from Gunicorn's settings and maps them to PalfreyConfig.

        Attributes:
            CONFIG_KWARGS (dict[str, typing.Any]): Default Palfrey-specific
                configuration overrides.
        """

        CONFIG_KWARGS: dict[str, Any] = {"loop": "auto", "http": "auto"}

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """
            Initialize the worker and synchronize logging with Gunicorn's loggers.
            """
            super().__init__(*args, **kwargs)

            # Redirect Palfrey internal logging to Gunicorn's configured handlers
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

            # Map Gunicorn configurations to Palfrey parameters
            config_kwargs: dict[str, Any] = {
                "app": None,
                "log_config": None,
                "timeout_keep_alive": self.cfg.keepalive,
                "timeout_notify": self.timeout,
                "callback_notify": self.callback_notify,
                "limit_max_requests": self.max_requests,
                "forwarded_allow_ips": self.cfg.forwarded_allow_ips,
            }

            # Map SSL options if Gunicorn is configured for HTTPS
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

            # Check for socket backlog settings
            backlog_setting = self.cfg.settings.get("backlog")
            if backlog_setting is not None and backlog_setting.value:
                config_kwargs["backlog"] = backlog_setting.value

            config_kwargs.update(self.CONFIG_KWARGS)
            self.config = PalfreyConfig(**config_kwargs)

        def init_signals(self) -> None:
            """
            Reset and configure signal handlers within the worker process.

            Overrides Gunicorn's signal setup to ensure compatibility between
            asyncio's signal loop and Gunicorn's process management.
            """
            for sig in self.SIGNALS:
                signal.signal(sig, signal.SIG_DFL)

            signal.signal(SIGUSR1_SIGNAL, self.handle_usr1)
            if hasattr(signal, "siginterrupt"):
                signal.siginterrupt(SIGUSR1_SIGNAL, False)

        def _install_sigquit_handler(self) -> None:
            """
            Register a handler for SIGQUIT within the running event loop.

            This enables graceful shutdown when Gunicorn sends SIGQUIT to the worker.
            """
            loop = asyncio.get_running_loop()
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(SIGQUIT_SIGNAL, self.handle_exit, SIGQUIT_SIGNAL, None)

        async def _serve(self) -> None:
            """
            Start the Palfrey server instance using sockets inherited from Gunicorn.
            """
            # Assign the application loaded by Gunicorn to the Palfrey config
            self.config.app = self.wsgi
            server = PalfreyServer(config=self.config)

            self._install_sigquit_handler()

            # Use pre-bound sockets from the Gunicorn arbiter
            await server.serve(sockets=self.sockets)

            if not server.started:
                # If the server failed to boot, exit with the worker boot error code
                exit_code = _WORKER_BOOT_ERROR if _WORKER_BOOT_ERROR is not None else 1
                sys.exit(exit_code)

        def run(self) -> None:
            """
            Execute the worker's main execution loop.

            Initializes the event loop policy and starts the asynchronous serve routine.
            """
            resolve_loop_setup(self.config.loop)()
            asyncio.run(self._serve())

        async def callback_notify(self) -> None:
            """
            Periodic notification bridge to maintain the Gunicorn heartbeat.

            This callback is invoked by the Palfrey server and calls Gunicorn's
            internal `notify` to prevent the arbiter from killing the worker.
            """
            self.notify()

    class PalfreyH11Worker(PalfreyWorker):
        """
        A specific Gunicorn worker variant that forces the H11 HTTP parser.

        This variant explicitly uses the standard asyncio event loop and
        the pure-Python H11 parser instead of the 'auto' resolution.
        """

        CONFIG_KWARGS = {"loop": "asyncio", "http": "h11"}

else:
    # Fallback assignment when Gunicorn is not present in the environment
    PalfreyWorker = _MissingGunicornWorker
    PalfreyH11Worker = _MissingGunicornWorker
