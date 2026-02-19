"""Palfrey command-line interface.

The CLI is implemented with Click and mirrors Uvicorn-confirmed option names so
users can migrate without relearning flag semantics.
"""

from __future__ import annotations

import os
import platform
import ssl
from copy import deepcopy
from typing import Any, get_args

import click

from palfrey import __version__
from palfrey.config import (
    LOGGING_CONFIG,
    KnownHTTPType,
    KnownInterfaceType,
    KnownLifespanMode,
    KnownLoopType,
    KnownWSType,
    PalfreyConfig,
)
from palfrey.importer import AppImportError
from palfrey.runtime import run

LOG_LEVEL_NAMES = ("critical", "error", "warning", "info", "debug", "trace")
LEVEL_CHOICES = click.Choice(list(LOG_LEVEL_NAMES))
LIFESPAN_CHOICES = click.Choice(list(get_args(KnownLifespanMode)))
INTERFACE_CHOICES = click.Choice(list(get_args(KnownInterfaceType)))


def _metavar_from_type(_type: Any) -> str:
    return f"[{'|'.join(key for key in get_args(_type) if key != 'none')}]"


def _mirror_uvicorn_envvars() -> list[str]:
    """Mirror ``UVICORN_*`` values into ``PALFREY_*`` when missing.

    This preserves Palfrey's native env-var prefix while keeping drop-in
    compatibility with existing Uvicorn-oriented shell environments.
    """

    mirrored_keys: list[str] = []
    for key, value in tuple(os.environ.items()):
        if not key.startswith("UVICORN_"):
            continue
        palfrey_key = "PALFREY_" + key[len("UVICORN_") :]
        if palfrey_key in os.environ:
            continue
        os.environ[palfrey_key] = value
        mirrored_keys.append(palfrey_key)
    return mirrored_keys


def _restore_mirrored_envvars(keys: list[str]) -> None:
    for key in keys:
        os.environ.pop(key, None)


class _DualPrefixCommand(click.Command):
    """Click command that refreshes Uvicorn env-var aliases before parsing."""

    def main(self, *args, **kwargs):
        mirrored_keys = _mirror_uvicorn_envvars()
        try:
            return super().main(*args, **kwargs)
        finally:
            _restore_mirrored_envvars(mirrored_keys)


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


@click.command(cls=_DualPrefixCommand, context_settings={"auto_envvar_prefix": "PALFREY"})
@click.argument("app", required=True, envvar=["PALFREY_APP", "UVICORN_APP"])
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    type=str,
    help="Bind socket to this host.",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=int,
    help="Bind socket to this port. If 0, an available port will be picked.",
)
@click.option(
    "--uds",
    default=None,
    type=str,
    help="Bind to a UNIX domain socket.",
)
@click.option("--fd", default=None, type=int, help="Bind to socket from this file descriptor.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload.")
@click.option(
    "--reload-dir",
    "reload_dirs",
    multiple=True,
    type=click.Path(path_type=str, exists=True),
    help="Set reload directories explicitly, instead of using the current working directory.",
)
@click.option(
    "--reload-include",
    "reload_includes",
    multiple=True,
    type=str,
    help="Set glob patterns to include while watching for files. Includes '*.py' "
    "by default; these defaults can be overridden with `--reload-exclude`. "
    "This option has no effect unless watchfiles is installed.",
)
@click.option(
    "--reload-exclude",
    "reload_excludes",
    multiple=True,
    type=str,
    help="Set glob patterns to exclude while watching for files. Includes "
    "'.*, .py[cod], .sw.*, ~*' by default; these defaults can be overridden "
    "with `--reload-include`. This option has no effect unless watchfiles is "
    "installed.",
)
@click.option(
    "--reload-delay",
    default=0.25,
    show_default=True,
    type=float,
    help="Delay between previous and next check if application needs to be. Defaults to 0.25s.",
)
@click.option(
    "--workers",
    default=None,
    type=int,
    help="Number of worker processes. Defaults to the $WEB_CONCURRENCY environment"
    " variable if available, or 1. Not valid with --reload.",
)
@click.option(
    "--loop",
    default="auto",
    show_default=True,
    type=str,
    metavar=_metavar_from_type(KnownLoopType),
    help="Event loop factory implementation.",
)
@click.option(
    "--http",
    default="auto",
    show_default=True,
    type=str,
    metavar=_metavar_from_type(KnownHTTPType),
    help="HTTP protocol implementation.",
)
@click.option(
    "--ws",
    default="auto",
    show_default=True,
    type=str,
    metavar=_metavar_from_type(KnownWSType),
    help="WebSocket protocol implementation.",
)
@click.option(
    "--ws-max-size",
    default=16_777_216,
    show_default=True,
    type=int,
    help="WebSocket max size message in bytes",
)
@click.option(
    "--ws-max-queue",
    default=32,
    show_default=True,
    type=int,
    help="The maximum length of the WebSocket message queue.",
)
@click.option(
    "--ws-ping-interval",
    default=20.0,
    show_default=True,
    type=float,
    help="WebSocket ping interval in seconds.",
)
@click.option(
    "--ws-ping-timeout",
    default=20.0,
    show_default=True,
    type=float,
    help="WebSocket ping timeout in seconds.",
)
@click.option(
    "--ws-per-message-deflate",
    type=bool,
    default=True,
    show_default=True,
    help="WebSocket per-message-deflate compression",
)
@click.option(
    "--lifespan",
    default="auto",
    show_default=True,
    type=LIFESPAN_CHOICES,
    help="Lifespan implementation.",
)
@click.option(
    "--interface",
    default="auto",
    show_default=True,
    type=INTERFACE_CHOICES,
    help="Select ASGI3, ASGI2, or WSGI as the application interface.",
)
@click.option(
    "--env-file",
    default=None,
    show_default=True,
    type=click.Path(path_type=str, exists=True),
    help="Environment configuration file.",
)
@click.option(
    "--log-config",
    default=None,
    show_default=True,
    type=click.Path(path_type=str, exists=True),
    help="Logging configuration file. Supported formats: .ini, .json, .yaml.",
)
@click.option(
    "--log-level",
    default=None,
    type=LEVEL_CHOICES,
    show_default=True,
    help="Log level. [default: info]",
)
@click.option(
    "--access-log/--no-access-log",
    is_flag=True,
    default=True,
    help="Enable/Disable access log.",
)
@click.option(
    "--use-colors/--no-use-colors",
    is_flag=True,
    default=None,
    help="Enable/Disable colorized logging.",
)
@click.option(
    "--proxy-headers/--no-proxy-headers",
    is_flag=True,
    default=True,
    help="Enable/Disable X-Forwarded-Proto, X-Forwarded-For to populate url scheme and remote address info.",
)
@click.option(
    "--server-header/--no-server-header",
    is_flag=True,
    default=True,
    help="Enable/Disable default Server header.",
)
@click.option(
    "--date-header/--no-date-header",
    is_flag=True,
    default=True,
    help="Enable/Disable default Date header.",
)
@click.option(
    "--forwarded-allow-ips",
    default=None,
    type=str,
    help="Comma separated list of IP Addresses, IP Networks, or literals "
    "(e.g. UNIX Socket path) to trust with proxy headers. Defaults to the "
    "$FORWARDED_ALLOW_IPS environment variable if available, or '127.0.0.1'. "
    "The literal '*' means trust everything.",
)
@click.option(
    "--root-path",
    default="",
    type=str,
    help="Set the ASGI 'root_path' for applications submounted below a given URL path.",
)
@click.option(
    "--limit-concurrency",
    default=None,
    type=int,
    help="Maximum number of concurrent connections or tasks to allow, before issuing HTTP 503 responses.",
)
@click.option(
    "--backlog",
    default=2048,
    type=int,
    help="Maximum number of connections to hold in backlog",
)
@click.option(
    "--limit-max-requests",
    default=None,
    type=int,
    help="Maximum number of requests to service before terminating the process.",
)
@click.option(
    "--limit-max-requests-jitter",
    default=0,
    show_default=True,
    type=int,
    help="Maximum jitter to add to limit_max_requests."
    " Staggers worker restarts to avoid all workers restarting simultaneously.",
)
@click.option(
    "--timeout-keep-alive",
    default=5,
    show_default=True,
    type=int,
    help="Close Keep-Alive connections if no new data is received within this timeout (in seconds).",
)
@click.option(
    "--timeout-graceful-shutdown",
    default=None,
    type=int,
    help="Maximum number of seconds to wait for graceful shutdown.",
)
@click.option(
    "--timeout-worker-healthcheck",
    default=5,
    show_default=True,
    type=int,
    help="Maximum number of seconds to wait for a worker to respond to a healthcheck.",
)
@click.option(
    "--ssl-keyfile",
    default=None,
    show_default=True,
    type=str,
    help="SSL key file",
)
@click.option(
    "--ssl-certfile",
    default=None,
    show_default=True,
    type=str,
    help="SSL certificate file",
)
@click.option(
    "--ssl-keyfile-password",
    default=None,
    show_default=True,
    type=str,
    help="SSL keyfile password",
)
@click.option(
    "--ssl-version",
    default=int(ssl.PROTOCOL_TLS_SERVER),
    show_default=True,
    type=int,
    help="SSL version to use (see stdlib ssl module's)",
)
@click.option(
    "--ssl-cert-reqs",
    default=int(ssl.CERT_NONE),
    show_default=True,
    type=int,
    help="Whether client certificate is required (see stdlib ssl module's)",
)
@click.option(
    "--ssl-ca-certs",
    default=None,
    show_default=True,
    type=str,
    help="CA certificates file",
)
@click.option(
    "--ssl-ciphers",
    default="TLSv1",
    show_default=True,
    type=str,
    help="Ciphers to use (see stdlib ssl module's)",
)
@click.option(
    "--header",
    "headers",
    multiple=True,
    type=str,
    help="Specify custom default HTTP response headers as a Name:Value pair",
)
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Display the uvicorn version and exit.",
)
@click.option(
    "--app-dir",
    default="",
    show_default=True,
    type=str,
    help="Look for APP in the specified directory, by adding this to the PYTHONPATH."
    " Defaults to the current working directory.",
)
@click.option(
    "--h11-max-incomplete-event-size",
    default=None,
    type=int,
    help="For h11, the maximum number of bytes to buffer of an incomplete event.",
)
@click.option(
    "--factory",
    is_flag=True,
    default=False,
    show_default=True,
    help="Treat APP as an application factory, i.e. a () -> <ASGI app> callable.",
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
    ssl_version: int,
    ssl_cert_reqs: int,
    ssl_ca_certs: str | None,
    ssl_ciphers: str,
    headers: tuple[str, ...],
    app_dir: str,
    factory: bool,
    h11_max_incomplete_event_size: int | None,
) -> None:
    try:
        resolved_log_config: dict[str, Any] | str | None
        if log_config is None:
            resolved_log_config = deepcopy(LOGGING_CONFIG)
        else:
            resolved_log_config = log_config
        config = PalfreyConfig(
            app=app,
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
            reload_dirs=list(reload_dirs),
            reload_includes=list(reload_includes),
            reload_excludes=list(reload_excludes),
            reload_delay=reload_delay,
            workers=workers,
            env_file=env_file,
            log_config=resolved_log_config,
            log_level=log_level,
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
    except (AppImportError, ImportError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
