"""Top-level runtime orchestration for Palfrey."""

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
    """Apply event loop policy according to configured mode."""

    resolve_loop_setup(loop_mode)()


def _normalize_cli_list(value: list[str] | str | None) -> list[str]:
    """Normalize run() list-or-string API values into list form."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _run_config(config: PalfreyConfig) -> PalfreyServer | None:
    """Run Palfrey according to supervision and runtime configuration.

    Args:
        config: Runtime options.

    Raises:
        RuntimeError: If incompatible options are selected.
    """

    load_env_file(config.env_file)
    _configure_loop(config.loop)

    if config.reload and config.workers_count > 1:
        logger.warning('"workers" flag is ignored when reloading is enabled.')

    if (config.reload or config.workers_count > 1) and not isinstance(config.app, str):
        raise RuntimeError(
            "You must pass the application as an import string to enable 'reload' or 'workers'."
        )

    bound_sockets: list[socket.socket] = []
    try:
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
        if config.workers_count > 1:
            parent_socket = config.bind_socket()
            bound_sockets = [parent_socket]
            WorkerSupervisor(config=config, sockets=bound_sockets).run()
            return None

        server = PalfreyServer(config)
        server.run()
        return server
    finally:
        for bound_socket in bound_sockets:
            with contextlib.suppress(OSError):
                bound_socket.close()
        if config.uds and os.path.exists(config.uds):
            os.remove(config.uds)


@overload
def run(config: PalfreyConfig) -> None:
    """Run Palfrey from a pre-built configuration."""


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
    """Run Palfrey from an application callable/import string and keyword options."""


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
    """Run Palfrey using a config object or direct app/kwargs inputs.

    Args:
        config_or_app: Either a ``PalfreyConfig`` instance or an app target.
        **kwargs: Configuration options when ``config_or_app`` is an app target.
    """
    if isinstance(config_or_app, PalfreyConfig):
        config = config_or_app
    else:
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

    if (
        server is not None
        and not server.started
        and not config.should_reload
        and config.workers_count == 1
    ):
        raise SystemExit(STARTUP_FAILURE)
