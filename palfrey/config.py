"""Typed configuration model for Palfrey runtime settings."""

from __future__ import annotations

import logging
import os
import ssl
from collections.abc import Awaitable, Callable
from configparser import RawConfigParser
from contextlib import suppress
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import IO, Any, Literal

from palfrey.acceleration import parse_header_items
from palfrey.types import AppType

KnownLoopType = Literal["none", "auto", "asyncio", "uvloop"]
LoopType = KnownLoopType | str
KnownHTTPType = Literal["auto", "h11", "httptools"]
HTTPType = KnownHTTPType | str
KnownWSType = Literal["auto", "none", "websockets", "websockets-sansio", "wsproto"]
WSType = KnownWSType | str
KnownLifespanMode = Literal["auto", "on", "off"]
LifespanMode = KnownLifespanMode | str
KnownInterfaceType = Literal["auto", "asgi3", "asgi2", "wsgi"]
InterfaceType = KnownInterfaceType | str
LogLevel = Literal["critical", "error", "warning", "info", "debug", "trace"]

KNOWN_LOOP_TYPES = {"none", "auto", "asyncio", "uvloop"}
KNOWN_HTTP_TYPES = {"auto", "h11", "httptools"}
KNOWN_WS_TYPES = {"auto", "none", "websockets", "websockets-sansio", "wsproto"}
KNOWN_LIFESPAN_MODES = {"auto", "on", "off"}
KNOWN_INTERFACE_TYPES = {"auto", "asgi3", "asgi2", "wsgi"}
KNOWN_LOG_LEVELS = {"critical", "error", "warning", "info", "debug", "trace"}
logger = logging.getLogger("palfrey.error")


def is_dir(path: Path) -> bool:
    """Return whether path resolves to a directory.

    Args:
        path: Path to validate.

    Returns:
        ``True`` when path exists and is a directory.
    """

    try:
        if not path.is_absolute():
            path = path.resolve()
        return path.is_dir()
    except OSError:
        return False


def resolve_reload_patterns(
    patterns_list: list[str],
    directories_list: list[str],
) -> tuple[list[str], list[Path]]:
    """Resolve reload glob patterns and directory roots.

    Args:
        patterns_list: Glob patterns provided by user.
        directories_list: Explicit directory entries.

    Returns:
        A tuple of normalized patterns and resolved root directories.
    """

    directories: list[Path] = list(set(map(Path, directories_list.copy())))
    patterns: list[str] = patterns_list.copy()

    current_working_directory = Path.cwd()
    for pattern in patterns_list:
        if pattern == ".*":
            continue
        patterns.append(pattern)
        if is_dir(Path(pattern)):
            directories.append(Path(pattern))
        else:
            for match in current_working_directory.glob(pattern):
                if is_dir(match):
                    directories.append(match)

    directories = list(set(directories))
    directories = [Path(path).resolve() for path in directories]
    directories = list({path for path in directories if is_dir(path)})

    nested_children: list[Path] = []
    for index, first in enumerate(directories):
        for second in directories[index + 1 :]:
            if first in second.parents:
                nested_children.append(second)
            elif second in first.parents:
                nested_children.append(first)

    directories = list(set(directories).difference(set(nested_children)))
    return list(set(patterns)), directories


def _normalize_dirs(dirs: list[str] | str | None) -> list[str]:
    """Normalize optional string-or-list directory values.

    Args:
        dirs: Optional scalar/list value.

    Returns:
        List of normalized values.
    """

    if dirs is None:
        return []
    if isinstance(dirs, str):
        return [dirs]
    return list(set(dirs))


def _module_available(module_name: str) -> bool:
    """Return whether a module can be imported in current environment."""

    return find_spec(module_name) is not None


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
    workers: int | None = None
    env_file: str | os.PathLike[str] | None = None
    log_config: dict[str, Any] | str | RawConfigParser | IO[Any] | None = None
    log_level: LogLevel | int | str | None = None
    access_log: bool = True
    proxy_headers: bool = True
    server_header: bool = True
    date_header: bool = True
    forwarded_allow_ips: list[str] | str | None = None
    root_path: str = ""
    limit_concurrency: int | None = None
    backlog: int = 2048
    limit_max_requests: int | None = None
    limit_max_requests_jitter: int = 0
    timeout_keep_alive: int = 5
    timeout_notify: int = 30
    timeout_graceful_shutdown: int | None = None
    timeout_worker_healthcheck: int = 5
    callback_notify: Callable[..., Awaitable[None]] | None = None
    ssl_keyfile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile_password: str | None = None
    ssl_version: int = int(ssl.PROTOCOL_TLS_SERVER)
    ssl_cert_reqs: int = int(ssl.CERT_NONE)
    ssl_ca_certs: str | None = None
    ssl_ciphers: str = "TLSv1"
    headers: list[tuple[str, str]] | list[str] | None = field(default_factory=list)
    use_colors: bool | None = None
    app_dir: str | None = ""
    factory: bool = False
    h11_max_incomplete_event_size: int | None = None
    _normalized_headers_cache: list[tuple[str, str]] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Normalize environment-dependent defaults and user inputs."""

        if ":" not in self.loop:
            self.loop = self.loop.lower()
        self.http = self.http.lower()
        self.ws = self.ws.lower()
        self.lifespan = self.lifespan.lower()
        self.interface = self.interface.lower()
        if isinstance(self.log_level, str):
            lowered = self.log_level.lower()
            if lowered not in KNOWN_LOG_LEVELS:
                raise ValueError(f"Unsupported log level: {self.log_level}")
            self.log_level = lowered

        if self.loop not in KNOWN_LOOP_TYPES and ":" not in self.loop:
            raise ValueError(f"Unsupported loop mode: {self.loop}")
        if self.http not in KNOWN_HTTP_TYPES:
            raise ValueError(f"Unsupported HTTP mode: {self.http}")
        if self.ws not in KNOWN_WS_TYPES:
            raise ValueError(f"Unsupported WebSocket mode: {self.ws}")
        if self.lifespan not in KNOWN_LIFESPAN_MODES:
            raise ValueError(f"Unsupported lifespan mode: {self.lifespan}")
        if self.interface not in KNOWN_INTERFACE_TYPES:
            raise ValueError(f"Unsupported interface mode: {self.interface}")

        if self.workers is None:
            web_concurrency = os.getenv("WEB_CONCURRENCY")
            self.workers = int(web_concurrency) if web_concurrency else 1
        elif self.workers < 1:
            raise ValueError("workers must be >= 1")

        if self.limit_max_requests_jitter < 0:
            raise ValueError("limit_max_requests_jitter must be >= 0")

        if self.forwarded_allow_ips is None:
            self.forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")

        if (
            self.reload_dirs or self.reload_includes or self.reload_excludes
        ) and not self.should_reload:
            logger.warning(
                "Current configuration will not reload as not all conditions are met, please refer to documentation."
            )

        if self.should_reload:
            original_reload_dirs = _normalize_dirs(self.reload_dirs)
            normalized_reload_includes = _normalize_dirs(self.reload_includes)
            normalized_reload_excludes = _normalize_dirs(self.reload_excludes)

            self.reload_includes, resolved_reload_dirs = resolve_reload_patterns(
                normalized_reload_includes,
                original_reload_dirs,
            )
            self.reload_excludes, resolved_reload_dirs_excludes = resolve_reload_patterns(
                normalized_reload_excludes,
                [],
            )

            reload_dirs_tmp = resolved_reload_dirs.copy()
            for excluded_dir in resolved_reload_dirs_excludes:
                for reload_dir in reload_dirs_tmp:
                    if excluded_dir == reload_dir or excluded_dir in reload_dir.parents:
                        with suppress(ValueError):
                            resolved_reload_dirs.remove(reload_dir)

            for pattern in self.reload_excludes:
                if pattern in self.reload_includes:
                    self.reload_includes.remove(pattern)

            if not resolved_reload_dirs:
                if original_reload_dirs:
                    logger.warning(
                        "Provided reload directories %s did not contain valid directories, watching current working directory.",
                        original_reload_dirs,
                    )
                resolved_reload_dirs = [Path.cwd()]

            self.reload_dirs = sorted(str(path) for path in resolved_reload_dirs)
            logger.info("Will watch for changes in these directories: %s", self.reload_dirs)
        else:
            self.reload_dirs = _normalize_dirs(self.reload_dirs)
            self.reload_includes = _normalize_dirs(self.reload_includes)
            self.reload_excludes = _normalize_dirs(self.reload_excludes)

        if self.app_dir is not None:
            self.app_dir = str(Path(self.app_dir).resolve())

        if not self.headers:
            self._normalized_headers_cache = []
        else:
            first_item = self.headers[0]
            if isinstance(first_item, tuple):
                self._normalized_headers_cache = [
                    (str(name), str(value)) for name, value in self.headers
                ]
            else:
                self._normalized_headers_cache = parse_header_items(
                    [str(item) for item in self.headers]
                )

    @property
    def normalized_headers(self) -> list[tuple[str, str]]:
        """Return normalized response headers configured via CLI or API."""

        return self._normalized_headers_cache

    @property
    def workers_count(self) -> int:
        """Return effective worker process count."""

        return self.workers or 1

    @property
    def effective_http(self) -> KnownHTTPType:
        """Return concrete HTTP backend mode after resolving ``auto``."""

        if self.http == "auto":
            return "httptools" if _module_available("httptools") else "h11"
        return self.http  # type: ignore[return-value]

    @property
    def effective_ws(self) -> KnownWSType:
        """Return concrete WebSocket backend mode after resolving ``auto``."""

        if self.interface == "wsgi":
            return "none"
        if self.ws == "auto":
            if _module_available("websockets"):
                return "websockets"
            if _module_available("wsproto"):
                return "wsproto"
            return "none"
        return self.ws  # type: ignore[return-value]

    @property
    def is_ssl(self) -> bool:
        """Return whether TLS options are configured."""

        return bool(self.ssl_keyfile or self.ssl_certfile)

    @property
    def should_reload(self) -> bool:
        """Return whether reload supervisor mode should be used."""

        return isinstance(self.app, str) and self.reload

    @property
    def use_subprocess(self) -> bool:
        """Return whether runtime requires subprocess supervision."""

        return bool(self.reload or self.workers_count > 1)

    @property
    def asgi_version(self) -> Literal["2.0", "3.0"]:
        """Return ASGI version string implied by selected interface."""

        mapping: dict[str, Literal["2.0", "3.0"]] = {
            "asgi2": "2.0",
            "asgi3": "3.0",
            "wsgi": "3.0",
        }
        return mapping[self.interface]

    @classmethod
    def from_import_string(
        cls,
        app: str,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        app_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> PalfreyConfig:
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

        options: dict[str, Any] = {
            "app": app,
            "host": host,
            "port": port,
            "app_dir": str(app_dir) if app_dir is not None else None,
        }
        options.update(kwargs)
        return cls(**options)


Config = PalfreyConfig
