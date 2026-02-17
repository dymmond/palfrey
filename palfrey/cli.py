"""Palfrey command-line interface.

The CLI is implemented with Click and mirrors Uvicorn-confirmed option names so
users can migrate without relearning flag semantics.
"""

from __future__ import annotations

import platform
from typing import cast

import click

from palfrey import __version__
from palfrey.config import (
    HTTPType,
    InterfaceType,
    LifespanMode,
    LogLevel,
    LoopType,
    PalfreyConfig,
    WSType,
)
from palfrey.runtime import run


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print detailed version output and exit.

    `--version` callback shape and output fields.
    """

    if not value or ctx.resilient_parsing:
        return

    py_implementation = platform.python_implementation()
    py_version = platform.python_version()
    system = platform.system()
    click.echo(f"Running palfrey {__version__} with {py_implementation} {py_version} on {system}")
    ctx.exit()


@click.command(context_settings={"auto_envvar_prefix": "PALFREY"})
@click.argument("app", required=True)
@click.option("--host", default="127.0.0.1", show_default=True, type=str)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--uds", default=None, type=click.Path(path_type=str))
@click.option("--fd", default=None, type=int)
@click.option(
    "--loop",
    default="auto",
    show_default=True,
    type=click.Choice(["none", "auto", "asyncio", "uvloop"], case_sensitive=False),
)
@click.option(
    "--http",
    default="auto",
    show_default=True,
    type=click.Choice(["auto", "h11", "httptools"], case_sensitive=False),
)
@click.option(
    "--ws",
    default="auto",
    show_default=True,
    type=click.Choice(["auto", "none", "websockets", "wsproto"], case_sensitive=False),
)
@click.option("--ws-max-size", default=16_777_216, show_default=True, type=int)
@click.option("--ws-max-queue", default=32, show_default=True, type=int)
@click.option("--ws-ping-interval", default=20.0, show_default=True, type=float)
@click.option("--ws-ping-timeout", default=20.0, show_default=True, type=float)
@click.option(
    "--ws-per-message-deflate",
    type=bool,
    default=True,
    show_default=True,
)
@click.option(
    "--lifespan",
    default="auto",
    show_default=True,
    type=click.Choice(["auto", "on", "off"], case_sensitive=False),
)
@click.option(
    "--interface",
    default="auto",
    show_default=True,
    type=click.Choice(["auto", "asgi3", "asgi2", "wsgi"], case_sensitive=False),
)
@click.option("--reload", is_flag=True, default=False, show_default=True)
@click.option("--reload-dir", "reload_dirs", multiple=True, type=click.Path(path_type=str))
@click.option("--reload-include", "reload_includes", multiple=True, type=str)
@click.option("--reload-exclude", "reload_excludes", multiple=True, type=str)
@click.option("--reload-delay", default=0.25, show_default=True, type=float)
@click.option("--workers", default=None, type=int)
@click.option("--env-file", default=None, type=click.Path(path_type=str))
@click.option("--log-config", default=None, type=click.Path(path_type=str))
@click.option(
    "--log-level",
    default=None,
    type=click.Choice(
        ["critical", "error", "warning", "info", "debug", "trace"],
        case_sensitive=False,
    ),
)
@click.option("--access-log/--no-access-log", default=True, show_default=True)
@click.option("--use-colors/--no-use-colors", default=None)
@click.option("--proxy-headers/--no-proxy-headers", default=True, show_default=True)
@click.option("--server-header/--no-server-header", default=True, show_default=True)
@click.option("--date-header/--no-date-header", default=True, show_default=True)
@click.option("--forwarded-allow-ips", default=None, type=str)
@click.option("--root-path", default="", show_default=True, type=str)
@click.option("--limit-concurrency", default=None, type=int)
@click.option("--backlog", default=2048, show_default=True, type=int)
@click.option("--limit-max-requests", default=None, type=int)
@click.option("--limit-max-requests-jitter", default=0, show_default=True, type=int)
@click.option("--timeout-keep-alive", default=5, show_default=True, type=int)
@click.option("--timeout-graceful-shutdown", default=None, type=int)
@click.option("--timeout-worker-healthcheck", default=5, show_default=True, type=int)
@click.option("--ssl-keyfile", default=None, type=click.Path(path_type=str))
@click.option("--ssl-certfile", default=None, type=click.Path(path_type=str))
@click.option("--ssl-keyfile-password", default=None, type=str)
@click.option("--ssl-version", default=None, type=int)
@click.option("--ssl-cert-reqs", default=None, type=int)
@click.option("--ssl-ca-certs", default=None, type=click.Path(path_type=str))
@click.option("--ssl-ciphers", default="TLSv1", show_default=True, type=str)
@click.option("--header", "headers", multiple=True, type=str)
@click.option("--app-dir", default="", type=click.Path(path_type=str))
@click.option("--factory", is_flag=True, default=False)
@click.option("--h11-max-incomplete-event-size", default=None, type=int)
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
)
def main(
    app: str,
    host: str,
    port: int,
    uds: str | None,
    fd: int | None,
    loop: str,
    http: str,
    ws: str,
    ws_max_size: int,
    ws_max_queue: int,
    ws_ping_interval: float,
    ws_ping_timeout: float,
    ws_per_message_deflate: bool,
    lifespan: str,
    interface: str,
    reload: bool,
    reload_dirs: tuple[str, ...],
    reload_includes: tuple[str, ...],
    reload_excludes: tuple[str, ...],
    reload_delay: float,
    workers: int | None,
    env_file: str | None,
    log_config: str | None,
    log_level: str | None,
    access_log: bool,
    use_colors: bool | None,
    proxy_headers: bool,
    server_header: bool,
    date_header: bool,
    forwarded_allow_ips: str | None,
    root_path: str,
    limit_concurrency: int | None,
    backlog: int,
    limit_max_requests: int | None,
    limit_max_requests_jitter: int,
    timeout_keep_alive: int,
    timeout_graceful_shutdown: int | None,
    timeout_worker_healthcheck: int,
    ssl_keyfile: str | None,
    ssl_certfile: str | None,
    ssl_keyfile_password: str | None,
    ssl_version: int | None,
    ssl_cert_reqs: int | None,
    ssl_ca_certs: str | None,
    ssl_ciphers: str,
    headers: tuple[str, ...],
    app_dir: str,
    factory: bool,
    h11_max_incomplete_event_size: int | None,
) -> None:
    """Run Palfrey using Uvicorn-compatible CLI options.

    Args:
        app: Application import string in ``module:attribute`` format.
        host: Bind host.
        port: Bind port.
        uds: Optional unix domain socket path.
        fd: Optional existing file descriptor.
        loop: Event loop implementation mode.
        http: HTTP parser mode.
        ws: WebSocket implementation mode.
        ws_max_size: Maximum websocket frame size in bytes.
        ws_max_queue: Maximum websocket queue depth.
        ws_ping_interval: Ping interval for managed websocket backends.
        ws_ping_timeout: Ping timeout for managed websocket backends.
        ws_per_message_deflate: Per-message-deflate toggle.
        lifespan: Lifespan mode.
        interface: Application interface mode.
        reload: Enable reload supervisor.
        reload_dirs: Directories watched in reload mode.
        reload_includes: Include globs for reload mode.
        reload_excludes: Exclude globs for reload mode.
        reload_delay: Reload polling interval.
        workers: Worker process count.
        env_file: Optional environment file path.
        log_config: Optional JSON logging config path.
        log_level: Runtime log level.
        access_log: Access log toggle.
        use_colors: Colorized logging toggle.
        proxy_headers: Proxy header support toggle.
        server_header: Default server header toggle.
        date_header: Default date header toggle.
        forwarded_allow_ips: Trusted proxy IP list.
        root_path: ASGI root path.
        limit_concurrency: Max active task count.
        backlog: Socket backlog.
        limit_max_requests: Shutdown after processing this many requests.
        limit_max_requests_jitter: Maximum restart jitter for max-requests shutdown.
        timeout_keep_alive: Keep-alive idle timeout in seconds.
        timeout_graceful_shutdown: Graceful shutdown timeout.
        timeout_worker_healthcheck: Worker health timeout.
        ssl_keyfile: TLS key path.
        ssl_certfile: TLS certificate path.
        ssl_keyfile_password: TLS key password.
        ssl_version: TLS protocol version integer.
        ssl_cert_reqs: TLS cert requirement mode integer.
        ssl_ca_certs: TLS CA bundle path.
        ssl_ciphers: TLS cipher suite string.
        headers: Additional static response headers.
        app_dir: Additional import search path.
        factory: Treat app target as factory.
        h11_max_incomplete_event_size: Maximum request head size.
    """

    config = PalfreyConfig(
        app=app,
        host=host,
        port=port,
        uds=uds,
        fd=fd,
        loop=cast(LoopType, loop),
        http=cast(HTTPType, http),
        ws=cast(WSType, ws),
        ws_max_size=ws_max_size,
        ws_max_queue=ws_max_queue,
        ws_ping_interval=ws_ping_interval,
        ws_ping_timeout=ws_ping_timeout,
        ws_per_message_deflate=ws_per_message_deflate,
        lifespan=cast(LifespanMode, lifespan),
        interface=cast(InterfaceType, interface),
        reload=reload,
        reload_dirs=list(reload_dirs),
        reload_includes=list(reload_includes),
        reload_excludes=list(reload_excludes),
        reload_delay=reload_delay,
        workers=workers,
        env_file=env_file,
        log_config=log_config,
        log_level=cast(LogLevel | None, log_level),
        access_log=access_log,
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
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        timeout_worker_healthcheck=timeout_worker_healthcheck,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        ssl_keyfile_password=ssl_keyfile_password,
        ssl_version=ssl_version,
        ssl_cert_reqs=ssl_cert_reqs,
        ssl_ca_certs=ssl_ca_certs,
        ssl_ciphers=ssl_ciphers,
        headers=list(headers),
        use_colors=use_colors,
        app_dir=app_dir,
        factory=factory,
        h11_max_incomplete_event_size=h11_max_incomplete_event_size,
    )
    run(config)
