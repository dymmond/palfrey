"""Typed configuration model for Palfrey runtime settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from palfrey.acceleration import parse_header_items
from palfrey.types import AppType

LoopType = Literal["none", "auto", "asyncio", "uvloop"]
HTTPType = Literal["auto", "h11", "httptools"]
WSType = Literal["auto", "none", "websockets", "wsproto"]
LifespanMode = Literal["auto", "on", "off"]
InterfaceType = Literal["auto", "asgi3", "asgi2", "wsgi"]
LogLevel = Literal["critical", "error", "warning", "info", "debug", "trace"]


@dataclass(slots=True)
class PalfreyConfig:
    """Configuration for server startup, protocol handling, and supervision.

    This model intentionally mirrors confirmed Uvicorn flags so CLI and Python
    APIs remain behavior-compatible where Palfrey has parity coverage.
    """

    app: AppType
    host: str = "127.0.0.1"
    port: int = 8000
    uds: str | None = None
    fd: int | None = None
    loop: LoopType = "auto"
    http: HTTPType = "auto"
    ws: WSType = "auto"
    ws_max_size: int = 16_777_216
    ws_max_queue: int = 32
    ws_ping_interval: float | None = 20.0
    ws_ping_timeout: float | None = 20.0
    ws_per_message_deflate: bool = True
    lifespan: LifespanMode = "auto"
    interface: InterfaceType = "auto"
    reload: bool = False
    reload_dirs: list[str] = field(default_factory=list)
    reload_includes: list[str] = field(default_factory=list)
    reload_excludes: list[str] = field(default_factory=list)
    reload_delay: float = 0.25
    workers: int = 1
    env_file: str | None = None
    log_config: str | None = None
    log_level: LogLevel | None = None
    access_log: bool = True
    proxy_headers: bool = True
    server_header: bool = True
    date_header: bool = True
    forwarded_allow_ips: str | None = None
    root_path: str = ""
    limit_concurrency: int | None = None
    backlog: int = 2048
    limit_max_requests: int | None = None
    timeout_keep_alive: int = 5
    timeout_graceful_shutdown: int | None = None
    timeout_worker_healthcheck: int = 5
    ssl_keyfile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile_password: str | None = None
    ssl_version: int | None = None
    ssl_cert_reqs: int | None = None
    ssl_ca_certs: str | None = None
    ssl_ciphers: str = "TLSv1"
    headers: list[tuple[str, str]] | list[str] = field(default_factory=list)
    use_colors: bool | None = None
    app_dir: str | None = None
    factory: bool = False
    h11_max_incomplete_event_size: int | None = None

    @property
    def normalized_headers(self) -> list[tuple[str, str]]:
        """Return normalized response headers configured via CLI or API."""

        if not self.headers:
            return []

        first_item = self.headers[0]
        if isinstance(first_item, tuple):
            return [(str(name), str(value)) for name, value in self.headers]

        return parse_header_items([str(item) for item in self.headers])

    @classmethod
    def from_import_string(
        cls,
        app: str,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        app_dir: str | Path | None = None,
        **kwargs: object,
    ) -> "PalfreyConfig":
        """Build a config from a `module:attribute` import target.

        Args:
            app: Import path in `module:attribute` format.
            host: Bind host.
            port: Bind port.
            app_dir: Optional application import directory.
            **kwargs: Additional configuration options.

        Returns:
            A configured ``PalfreyConfig`` instance.
        """

        return cls(
            app=app,
            host=host,
            port=port,
            app_dir=str(app_dir) if app_dir is not None else None,
            **kwargs,
        )
