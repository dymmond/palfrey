from __future__ import annotations

import contextlib
import os
import socket
import ssl
import sys
from collections.abc import Awaitable, Callable
from configparser import RawConfigParser
from copy import deepcopy
from typing import IO, Any, overload

from palfrey.config import (
    LOGGING_CONFIG,
    HTTPType,
    InterfaceType,
    LifespanMode,
    LoopType,
    PalfreyConfig,
    WSType,
)
from palfrey.env import load_env_file
from palfrey.logging_config import get_logger
from palfrey.loops import resolve_loop_setup
from palfrey.server import PalfreyServer
from palfrey.supervisors.reload import ReloadSupervisor, build_reload_argv
from palfrey.supervisors.workers import WorkerSupervisor
from palfrey.types import AppType

logger = get_logger("palfrey.runtime")
STARTUP_FAILURE = 3


def _configure_loop(loop_mode: str) -> None:
    """
    Initialize and install the requested event loop policy.

    Args:
        loop_mode (str): The identifier for the loop implementation (e.g., "uvloop", "asyncio").
    """
    resolve_loop_setup(loop_mode)()


def _normalize_cli_list(value: list[str] | str | None) -> list[str]:
    """
    Ensure that configuration values intended as lists are properly typed.

    Args:
        value (list[str] | str | None): The input value which could be a single string,
            a list of strings, or None.

    Returns:
        list[str]: A list of strings. Returns an empty list if input is None.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _run_config(config: PalfreyConfig) -> PalfreyServer | None:
    """
    Execute the server startup logic based on the provided configuration object.

    This function determines whether to start a single server instance, a reload
    supervisor for development, or a worker supervisor for multi-process deployments.

    Args:
        config (PalfreyConfig): The fully initialized configuration for the runtime.

    Returns:
        PalfreyServer | None: The server instance if running in single-process mode,
            otherwise None if a supervisor has taken over the process execution.

    Raises:
        RuntimeError: If 'reload' or 'workers' is requested but the application
            is not provided as an import string.
    """
    load_env_file(config.env_file)
    _configure_loop(config.loop)

    if config.reload and config.workers_count > 1:
        logger.warning('"workers" flag is ignored when reloading is enabled.')

    # Multi-process or reload modes require an import string to re-import the app in children
    if (config.reload or config.workers_count > 1) and not isinstance(config.app, str):
        raise RuntimeError(
            "You must pass the application as an import string to enable 'reload' or 'workers'."
        )

    bound_sockets: list[socket.socket] = []
    try:
        # Check if we are the parent process responsible for spawning reloader children
        if config.should_reload and os.environ.get("PALFREY_RELOAD_CHILD") != "1":
            parent_socket = config.bind_socket()
            bound_sockets = [parent_socket]
            supervisor = ReloadSupervisor(
                config=config,
                argv=build_reload_argv(fd=parent_socket.fileno()),
                pass_fds=(parent_socket.fileno(),),
            )
            supervisor.run()
            return None

        # Handle multi-worker orchestration
        if config.workers_count > 1:
            parent_socket = config.bind_socket()
            bound_sockets = [parent_socket]
            WorkerSupervisor(config=config, sockets=bound_sockets).run()
            return None

        # Standard single-process server execution
        server = PalfreyServer(config)
        server.run()
        return server
    finally:
        # Ensure sockets are closed and Unix Domain Sockets are unlinked on exit
        for bound_socket in bound_sockets:
            with contextlib.suppress(OSError):
                bound_socket.close()
        if config.uds and os.path.exists(config.uds):
            os.remove(config.uds)


@overload
def run(config: PalfreyConfig) -> None:
    """
    Run Palfrey using a pre-constructed configuration object.

    Args:
        config (PalfreyConfig): An existing PalfreyConfig instance.
    """


@overload
def run(
    app: AppType,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    uds: str | None = None,
    fd: int | None = None,
    loop: LoopType = "auto",
    http: HTTPType = "auto",
    ws: WSType = "auto",
    ws_max_size: int = 16_777_216,
    ws_max_queue: int = 32,
    ws_ping_interval: float | None = 20.0,
    ws_ping_timeout: float | None = 20.0,
    ws_per_message_deflate: bool = True,
    lifespan: LifespanMode = "auto",
    interface: InterfaceType = "auto",
    reload: bool = False,
    reload_dirs: list[str] | str | None = None,
    reload_includes: list[str] | str | None = None,
    reload_excludes: list[str] | str | None = None,
    reload_delay: float = 0.25,
    workers: int | None = None,
    env_file: str | os.PathLike[str] | None = None,
    log_config: dict[str, Any] | str | RawConfigParser | IO[Any] | None = None,
    log_level: str | int | None = None,
    access_log: bool = True,
    use_colors: bool | None = None,
    proxy_headers: bool = True,
    server_header: bool = True,
    date_header: bool = True,
    forwarded_allow_ips: list[str] | str | None = None,
    root_path: str = "",
    limit_concurrency: int | None = None,
    backlog: int = 2048,
    limit_max_requests: int | None = None,
    limit_max_requests_jitter: int = 0,
    timeout_keep_alive: int = 5,
    timeout_notify: int = 30,
    timeout_graceful_shutdown: int | None = None,
    timeout_worker_healthcheck: int = 5,
    callback_notify: Callable[..., Awaitable[None]] | None = None,
    ssl_keyfile: str | os.PathLike[str] | None = None,
    ssl_certfile: str | os.PathLike[str] | None = None,
    ssl_keyfile_password: str | None = None,
    ssl_version: int = int(ssl.PROTOCOL_TLS_SERVER),
    ssl_cert_reqs: int = int(ssl.CERT_NONE),
    ssl_ca_certs: str | os.PathLike[str] | None = None,
    ssl_ciphers: str = "TLSv1",
    headers: list[tuple[str, str]] | None = None,
    app_dir: str | None = None,
    factory: bool = False,
    h11_max_incomplete_event_size: int | None = None,
) -> None:
    """
    Run Palfrey by passing an application and configuration options as keywords.
    """


def run(
    config_or_app: PalfreyConfig | AppType,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    uds: str | None = None,
    fd: int | None = None,
    loop: LoopType = "auto",
    http: HTTPType = "auto",
    ws: WSType = "auto",
    ws_max_size: int = 16_777_216,
    ws_max_queue: int = 32,
    ws_ping_interval: float | None = 20.0,
    ws_ping_timeout: float | None = 20.0,
    ws_per_message_deflate: bool = True,
    lifespan: LifespanMode = "auto",
    interface: InterfaceType = "auto",
    reload: bool = False,
    reload_dirs: list[str] | str | None = None,
    reload_includes: list[str] | str | None = None,
    reload_excludes: list[str] | str | None = None,
    reload_delay: float = 0.25,
    workers: int | None = None,
    env_file: str | os.PathLike[str] | None = None,
    log_config: dict[str, Any] | str | RawConfigParser | IO[Any] | None = None,
    log_level: str | int | None = None,
    access_log: bool = True,
    use_colors: bool | None = None,
    proxy_headers: bool = True,
    server_header: bool = True,
    date_header: bool = True,
    forwarded_allow_ips: list[str] | str | None = None,
    root_path: str = "",
    limit_concurrency: int | None = None,
    backlog: int = 2048,
    limit_max_requests: int | None = None,
    limit_max_requests_jitter: int = 0,
    timeout_keep_alive: int = 5,
    timeout_notify: int = 30,
    timeout_graceful_shutdown: int | None = None,
    timeout_worker_healthcheck: int = 5,
    callback_notify: Callable[..., Awaitable[None]] | None = None,
    ssl_keyfile: str | os.PathLike[str] | None = None,
    ssl_certfile: str | os.PathLike[str] | None = None,
    ssl_keyfile_password: str | None = None,
    ssl_version: int = int(ssl.PROTOCOL_TLS_SERVER),
    ssl_cert_reqs: int = int(ssl.CERT_NONE),
    ssl_ca_certs: str | os.PathLike[str] | None = None,
    ssl_ciphers: str = "TLSv1",
    headers: list[tuple[str, str]] | None = None,
    app_dir: str | None = None,
    factory: bool = False,
    h11_max_incomplete_event_size: int | None = None,
) -> None:
    """
    Main entry point for running the Palfrey server.

    This function accepts either a pre-configured PalfreyConfig object or an
    application (callable or string) plus various keyword arguments to construct
    the configuration dynamically.

    Args:
        config_or_app (PalfreyConfig | AppType): The application or config instance.
        host (str): Bind socket to this host. Defaults to "127.0.0.1".
        port (int): Bind socket to this port. Defaults to 8000.
        uds (str | None): Bind to a UNIX domain socket. Defaults to None.
        fd (int | None): Bind to an existing file descriptor. Defaults to None.
        loop (LoopType): Event loop implementation. Defaults to "auto".
        http (HTTPType): HTTP protocol implementation. Defaults to "auto".
        ws (WSType): WebSocket protocol implementation. Defaults to "auto".
        reload (bool): Enable auto-reload on file changes. Defaults to False.
        workers (int | None): Number of worker processes. Defaults to None.
        log_config (dict[str, Any] | str | RawConfigParser | IO[Any] | None):
            Logging configuration dictionary or path. Defaults to None.
        **kwargs: Additional server tuning and SSL parameters.
    """
    if isinstance(config_or_app, PalfreyConfig):
        config = config_or_app
    else:
        # Construct config from keyword arguments if an app was provided directly
        config = PalfreyConfig(
            app=config_or_app,
            host=host,
            port=port,
            uds=uds,
            fd=fd,
            loop=loop,
            http=http,
            ws=ws,
            ws_max_size=ws_max_size,
            ws_max_queue=ws_max_queue,
            ws_ping_interval=ws_ping_interval,
            ws_ping_timeout=ws_ping_timeout,
            ws_per_message_deflate=ws_per_message_deflate,
            lifespan=lifespan,
            interface=interface,
            reload=reload,
            reload_dirs=_normalize_cli_list(reload_dirs),
            reload_includes=_normalize_cli_list(reload_includes),
            reload_excludes=_normalize_cli_list(reload_excludes),
            reload_delay=reload_delay,
            workers=workers,
            env_file=env_file,
            log_config=deepcopy(LOGGING_CONFIG) if log_config is None else log_config,
            log_level=log_level,
            access_log=access_log,
            use_colors=use_colors,
            proxy_headers=proxy_headers,
            server_header=server_header,
            date_header=date_header,
            forwarded_allow_ips=forwarded_allow_ips,
            root_path=root_path,
            limit_concurrency=limit_concurrency,
            backlog=backlog,
            limit_max_requests=limit_max_requests,
            limit_max_requests_jitter=limit_max_requests_jitter,
            timeout_keep_alive=timeout_keep_alive,
            timeout_notify=timeout_notify,
            timeout_graceful_shutdown=timeout_graceful_shutdown,
            timeout_worker_healthcheck=timeout_worker_healthcheck,
            callback_notify=callback_notify,
            ssl_keyfile=str(ssl_keyfile) if ssl_keyfile is not None else None,
            ssl_certfile=str(ssl_certfile) if ssl_certfile is not None else None,
            ssl_keyfile_password=ssl_keyfile_password,
            ssl_version=ssl_version,
            ssl_cert_reqs=ssl_cert_reqs,
            ssl_ca_certs=str(ssl_ca_certs) if ssl_ca_certs is not None else None,
            ssl_ciphers=ssl_ciphers,
            headers=headers,
            app_dir=app_dir,
            factory=factory,
            h11_max_incomplete_event_size=h11_max_incomplete_event_size,
        )

    # Ensure the application directory is in the python path for imports
    if config.app_dir is not None:
        sys.path.insert(0, config.app_dir)

    if (config.reload or config.workers_count > 1) and not isinstance(config.app, str):
        logger.warning(
            "You must pass the application as an import string to enable 'reload' or 'workers'."
        )
        raise SystemExit(1)

    try:
        server = _run_config(config)
    except KeyboardInterrupt:
        return

    # If the server failed to start in single-process mode, exit with a failure code
    if (
        server is not None
        and not server.started
        and not config.should_reload
        and config.workers_count == 1
    ):
        raise SystemExit(STARTUP_FAILURE)
