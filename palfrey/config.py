from __future__ import annotations

import asyncio
import logging
import os
import socket
import ssl
import sys
from collections.abc import Awaitable, Callable
from configparser import RawConfigParser
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import IO, Any, Literal, cast

import click

from palfrey.acceleration import parse_header_items
from palfrey.types import AppType

# Ensure AF_UNIX is defined for cross-platform compatibility where possible
SOCKET_AF_UNIX = getattr(socket, "AF_UNIX", socket.AF_INET)
if not hasattr(socket, "AF_UNIX"):
    socket.AF_UNIX = SOCKET_AF_UNIX

# Type Aliases for valid configuration options
KnownLoopType = Literal["none", "auto", "asyncio", "uvloop"]
LoopType = KnownLoopType | str
KnownHTTPType = Literal["auto", "h11", "httptools"]
HTTPType = KnownHTTPType | str | type[asyncio.Protocol]
KnownWSType = Literal["auto", "none", "websockets", "websockets-sansio", "wsproto"]
WSType = KnownWSType | str | type[asyncio.Protocol]
KnownLifespanMode = Literal["auto", "on", "off"]
LifespanMode = KnownLifespanMode | str
KnownInterfaceType = Literal["auto", "asgi3", "asgi2", "wsgi"]
InterfaceType = KnownInterfaceType | str
LogLevel = Literal["critical", "error", "warning", "info", "debug", "trace"]

# Validation sets for configuration parameters
KNOWN_LOOP_TYPES = {"none", "auto", "asyncio", "uvloop"}
KNOWN_HTTP_TYPES = {"auto", "h11", "httptools"}
KNOWN_WS_TYPES = {"auto", "none", "websockets", "websockets-sansio", "wsproto"}
KNOWN_LIFESPAN_MODES = {"auto", "on", "off"}
KNOWN_INTERFACE_TYPES = {"auto", "asgi3", "asgi2", "wsgi"}
KNOWN_LOG_LEVELS = {"critical", "error", "warning", "info", "debug", "trace"}

logger = logging.getLogger("palfrey.error")
TRACE_LOG_LEVEL = 5

LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "palfrey.logging_config.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "palfrey.logging_config.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "palfrey": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "palfrey.error": {"level": "INFO"},
        "palfrey.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


def is_dir(path: Path) -> bool:
    """
    Checks if a path object resolves to a valid directory on the filesystem.

    Args:
        path (Path): The filesystem path to investigate.

    Returns:
        bool: True if the path exists and is a directory; False otherwise.
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
    """
    Resolves and normalizes file glob patterns and directory roots for the reload supervisor.

    Args:
        patterns_list (list[str]): Glob patterns provided by the user for file watching.
        directories_list (list[str]): Explicit directory paths to be included in the watch.

    Returns:
        tuple[list[str], list[Path]]: A tuple containing a unique list of glob patterns and a
            list of resolved directory Path objects.
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

    # Eliminate child directories if their parent is already being watched
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
    """
    Normalizes mixed directory inputs into a flat list of strings.

    Args:
        dirs (list[str] | str | None): Directory input which may be a string, list, or None.

    Returns:
        list[str]: A unique list of directory path strings.
    """
    if dirs is None:
        return []
    if isinstance(dirs, str):
        return [dirs]
    return list(set(dirs))


def _module_available(module_name: str) -> bool:
    """
    Determines if a specific Python module can be imported in the current environment.

    Args:
        module_name (str): The name of the module to search for.

    Returns:
        bool: True if the module is found; False otherwise.
    """
    return find_spec(module_name) is not None


def create_ssl_context(
    certfile: str | os.PathLike[str],
    keyfile: str | os.PathLike[str] | None,
    password: str | None,
    ssl_version: int,
    cert_reqs: int,
    ca_certs: str | os.PathLike[str] | None,
    ciphers: str | None,
) -> ssl.SSLContext:
    """
    Constructs an SSLContext using standard Uvicorn/Palfrey configuration parameters.

    Args:
        certfile (str | os.PathLike[str]): Path to the certificate file.
        keyfile (str | os.PathLike[str] | None): Path to the private key file.
        password (str | None): Password for the key file, if applicable.
        ssl_version (int): The protocol version (e.g., ssl.PROTOCOL_TLS_SERVER).
        cert_reqs (int): Verify mode (e.g., ssl.CERT_REQUIRED).
        ca_certs (str | os.PathLike[str] | None): Path to CA bundle.
        ciphers (str | None): OpenSSL cipher suite string.

    Returns:
        ssl.SSLContext: A configured SSL context object ready for socket wrapping.
    """
    context = ssl.SSLContext(ssl_version)
    get_password = (lambda: password) if password else None
    context.load_cert_chain(certfile, keyfile, get_password)
    context.verify_mode = ssl.VerifyMode(cert_reqs)
    if ca_certs:
        context.load_verify_locations(ca_certs)
    if ciphers:
        context.set_ciphers(ciphers)
    return context


def _asyncio_loop_factory(
    use_subprocess: bool = False,
) -> Callable[[], asyncio.AbstractEventLoop]:
    """
    Returns an event loop factory for the standard asyncio implementation.

    Args:
        use_subprocess (bool): Whether the loop must support subprocess execution.

    Returns:
        Callable[[], asyncio.AbstractEventLoop]: The loop factory class or function.
    """
    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop


def _uvloop_loop_factory(
    use_subprocess: bool = False,
) -> Callable[[], asyncio.AbstractEventLoop]:
    """
    Returns an event loop factory for the uvloop implementation.

    Args:
        use_subprocess (bool): Ignored here but kept for signature parity.

    Returns:
        Callable[[], asyncio.AbstractEventLoop]: The uvloop loop factory.
    """
    import uvloop

    return uvloop.new_event_loop


def _auto_loop_factory(
    use_subprocess: bool = False,
) -> Callable[[], asyncio.AbstractEventLoop]:
    """
    Automatically selects the best available event loop factory.

    Prefers uvloop on supported platforms, falling back to standard asyncio.

    Args:
        use_subprocess (bool): Whether subprocess support is required.

    Returns:
        Callable[[], asyncio.AbstractEventLoop]: The chosen loop factory.
    """
    try:
        import uvloop  # noqa: F401
    except ImportError:
        return _asyncio_loop_factory(use_subprocess=use_subprocess)
    return _uvloop_loop_factory(use_subprocess=use_subprocess)


@dataclass(slots=True)
class PalfreyConfig:
    """
    The central configuration model for the Palfrey server runtime.

    This class encapsulates all settings related to networking, protocol handling,
    worker management, and security. It mirrors Uvicorn's configuration structure
    to maintain a familiar interface for users.
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
    log_config: dict[str, Any] | str | RawConfigParser | IO[Any] | None = field(
        default_factory=lambda: deepcopy(LOGGING_CONFIG)
    )
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
    loaded: bool = field(default=False, init=False)
    loaded_app: Any = field(default=None, init=False, repr=False)
    encoded_headers: list[tuple[bytes, bytes]] = field(default_factory=list, init=False, repr=False)
    ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)
    http_protocol_class: Any = field(default=None, init=False, repr=False)
    ws_protocol_class: Any = field(default=None, init=False, repr=False)
    lifespan_class: Any = field(default=None, init=False, repr=False)
    _normalized_headers_cache: list[tuple[str, str]] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """
        Normalizes and validates configuration settings after initialization.

        This method performs input sanitization, resolves environmental defaults
        (like worker count), and sets up directory watching parameters for the reloader.
        """
        if ":" not in self.loop:
            self.loop = self.loop.lower()
        if isinstance(self.http, str) and ":" not in self.http:
            self.http = self.http.lower()
        if isinstance(self.ws, str) and ":" not in self.ws:
            self.ws = self.ws.lower()
        self.lifespan = self.lifespan.lower()
        self.interface = self.interface.lower()

        if isinstance(self.log_level, str):
            lowered = self.log_level.lower()
            if lowered not in KNOWN_LOG_LEVELS:
                raise ValueError(f"Unsupported log level: {self.log_level}")
            self.log_level = lowered

        # Validate implementation modes against known allowed sets
        if self.loop not in KNOWN_LOOP_TYPES and ":" not in self.loop:
            raise ValueError(f"Unsupported loop mode: {self.loop}")
        if isinstance(self.http, str):
            if self.http not in KNOWN_HTTP_TYPES and ":" not in self.http:
                raise ValueError(f"Unsupported HTTP mode: {self.http}")
        if isinstance(self.ws, str):
            if self.ws not in KNOWN_WS_TYPES and ":" not in self.ws:
                raise ValueError(f"Unsupported WebSocket mode: {self.ws}")
        if self.lifespan not in KNOWN_LIFESPAN_MODES:
            raise ValueError(f"Unsupported lifespan mode: {self.lifespan}")
        if self.interface not in KNOWN_INTERFACE_TYPES:
            raise ValueError(f"Unsupported interface mode: {self.interface}")

        # Resolve worker count from environment if not explicitly provided
        if self.workers is None:
            web_concurrency = os.getenv("WEB_CONCURRENCY")
            self.workers = int(web_concurrency) if web_concurrency else 1
        elif self.workers < 1:
            raise ValueError("workers must be >= 1")

        if self.limit_max_requests_jitter < 0:
            raise ValueError("limit_max_requests_jitter must be >= 0")

        if self.forwarded_allow_ips is None:
            self.forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")

        # Handle reload logic and directory normalization
        if (
            self.reload_dirs or self.reload_includes or self.reload_excludes
        ) and not self.should_reload:
            logger.warning(
                "Current configuration will not reload as not all conditions are met, "
                "please refer to documentation."
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

            # Exclude directories as requested
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
                        "Provided reload directories %s did not contain valid directories, "
                        "watching current working directory.",
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

        # Normalize header cache
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
        """
        Returns the parsed and normalized list of custom HTTP headers.

        Returns:
            list[tuple[str, str]]: A list of (name, value) string pairs.
        """
        return self._normalized_headers_cache

    @property
    def workers_count(self) -> int:
        """
        Provides the effective number of worker processes to spawn.

        Returns:
            int: The worker count, defaulting to 1.
        """
        return self.workers or 1

    @property
    def effective_http(self) -> KnownHTTPType:
        """
        Resolves the concrete HTTP implementation to use when 'auto' is selected.

        Returns:
            KnownHTTPType: Either 'httptools' if available, or 'h11'.
        """
        if not isinstance(self.http, str):
            return "h11"
        if self.http == "auto":
            return "httptools" if _module_available("httptools") else "h11"
        if self.http in KNOWN_HTTP_TYPES:
            return self.http  # type: ignore[return-value]
        return "h11"

    @property
    def effective_ws(self) -> KnownWSType:
        """
        Resolves the concrete WebSocket implementation to use.

        Returns:
            KnownWSType: The resolved WebSocket backend or 'none' if inapplicable.
        """
        if self.interface == "wsgi":
            return "none"
        if not isinstance(self.ws, str):
            if _module_available("websockets"):
                return "websockets"
            if _module_available("wsproto"):
                return "wsproto"
            return "none"
        if self.ws == "auto":
            if _module_available("websockets"):
                return "websockets"
            if _module_available("wsproto"):
                return "wsproto"
            return "none"
        if self.ws in KNOWN_WS_TYPES:
            return self.ws  # type: ignore[return-value]
        if _module_available("websockets"):
            return "websockets"
        if _module_available("wsproto"):
            return "wsproto"
        return "none"

    @property
    def is_ssl(self) -> bool:
        """
        Indicates whether the configuration includes SSL/TLS parameters.

        Returns:
            bool: True if cert or key files are provided.
        """
        return bool(self.ssl_keyfile or self.ssl_certfile)

    @property
    def should_reload(self) -> bool:
        """
        Determines if the server should run in auto-reload mode.

        Returns:
            bool: True if reload is enabled and the app is provided as a string.
        """
        return isinstance(self.app, str) and self.reload

    @property
    def use_subprocess(self) -> bool:
        """
        Checks if the configuration requires spawning subprocesses.

        Returns:
            bool: True for reload mode or multiple workers.
        """
        return bool(self.reload or self.workers_count > 1)

    @property
    def asgi_version(self) -> Literal["2.0", "3.0"]:
        """
        Determines the ASGI version based on the selected interface.

        Returns:
            Literal["2.0", "3.0"]: The version string.
        """
        mapping: dict[str, Literal["2.0", "3.0"]] = {
            "asgi2": "2.0",
            "asgi3": "3.0",
            "wsgi": "3.0",
        }
        return mapping[self.interface]

    def bind_socket(self) -> socket.socket:
        """
        Creates and binds a server socket based on UDS, FD, or TCP configuration.

        Returns:
            socket.socket: A bound and inheritable socket object.

        Raises:
            SystemExit: If the socket cannot be bound.
        """
        logger_args: list[Any]
        if self.uds:
            sock = socket.socket(SOCKET_AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(self.uds)
                os.chmod(self.uds, 0o666)
            except OSError as exc:
                logger.error("%s", exc)
                raise SystemExit(1) from exc

            message = "Palfrey running on unix socket %s (Press CTRL+C to quit)"
            socket_name_format = "%s"
            color_message = (
                "Palfrey running on "
                + click.style(socket_name_format, bold=True)
                + " (Press CTRL+C to quit)"
            )
            logger_args = [self.uds]
        elif self.fd is not None:
            sock = socket.fromfd(self.fd, SOCKET_AF_UNIX, socket.SOCK_STREAM)
            message = "Palfrey running on socket %s (Press CTRL+C to quit)"
            socket_name_format = "%s"
            color_message = (
                "Palfrey running on "
                + click.style(socket_name_format, bold=True)
                + " (Press CTRL+C to quit)"
            )
            logger_args = [sock.getsockname()]
        else:
            family = socket.AF_INET6 if self.host and ":" in self.host else socket.AF_INET
            sock = socket.socket(family=family)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((self.host, self.port))
            except OSError as exc:
                logger.error("%s", exc)
                raise SystemExit(1) from exc

            protocol_name = "https" if self.is_ssl else "http"
            bound_port = int(sock.getsockname()[1])
            if family == socket.AF_INET6:
                address_format = "%s://[%s]:%d"
            else:
                address_format = "%s://%s:%d"
            message = f"Palfrey running on {address_format} (Press CTRL+C to quit)"
            color_message = (
                "Palfrey running on "
                + click.style(address_format, bold=True)
                + " (Press CTRL+C to quit)"
            )
            logger_args = [protocol_name, self.host, bound_port]

        logger.info(message, *logger_args, extra={"color_message": color_message})

        sock.set_inheritable(True)
        return sock

    def load(self) -> None:
        """
        Loads the application, protocol classes, and initializes the SSL context.

        This method triggers the actual importing of the application and the setup
        of the internal protocol classes used by the Palfrey worker.
        """
        assert not self.loaded

        if self.is_ssl:
            assert self.ssl_certfile
            self.ssl_context = create_ssl_context(
                certfile=self.ssl_certfile,
                keyfile=self.ssl_keyfile,
                password=self.ssl_keyfile_password,
                ssl_version=self.ssl_version,
                cert_reqs=self.ssl_cert_reqs,
                ca_certs=self.ssl_ca_certs,
                ciphers=self.ssl_ciphers,
            )
        else:
            self.ssl_context = None

        encoded = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in self.normalized_headers
        ]
        if self.server_header and b"server" not in dict(encoded):
            self.encoded_headers = [(b"server", b"palfrey")] + encoded
        else:
            self.encoded_headers = encoded

        # Deferred imports for runtime dependencies
        from palfrey.importer import (
            AppFactoryError,
            AppImportError,
            ImportFromStringError,
            _import_from_string,
            resolve_application,
        )
        from palfrey.lifespan import LifespanManager

        # Resolve HTTP protocol class
        if isinstance(self.http, str):
            if self.http in KNOWN_HTTP_TYPES:
                self.http_protocol_class = self.effective_http
            else:
                try:
                    self.http_protocol_class = _import_from_string(self.http)
                except ImportFromStringError as exc:
                    logger.error("Error loading HTTP protocol class. %s", exc)
                    raise SystemExit(1) from exc
        else:
            self.http_protocol_class = self.http

        # Resolve WebSocket protocol class
        if self.interface == "wsgi" or self.ws == "none":
            self.ws_protocol_class = None
        elif isinstance(self.ws, str):
            if self.ws in KNOWN_WS_TYPES:
                self.ws_protocol_class = self.effective_ws
            else:
                try:
                    self.ws_protocol_class = _import_from_string(self.ws)
                except ImportFromStringError as exc:
                    logger.error("Error loading WebSocket protocol class. %s", exc)
                    raise SystemExit(1) from exc
        else:
            self.ws_protocol_class = self.ws

        self.lifespan_class = None if self.lifespan == "off" else LifespanManager

        try:
            resolved = resolve_application(self)
        except AppFactoryError as exc:
            logger.error("Error loading ASGI app factory: %s", exc)
            raise SystemExit(1) from exc
        except AppImportError as exc:
            logger.error("Error loading ASGI app. %s", exc)
            raise SystemExit(1) from exc

        self.loaded_app = resolved.app
        self.interface = resolved.interface
        self.loaded = True

    def setup_event_loop(self) -> None:
        """
        A deprecated method placeholder to match historical Uvicorn interface parity.

        Raises:
            AttributeError: Instructs user to use get_loop_factory.
        """
        raise AttributeError(
            "The `setup_event_loop` method was replaced by `get_loop_factory` in uvicorn 0.36.0.\n"
            "None of those methods are supposed to be used directly. If you are doing it, "
            "please let me know here: https://github.com/Kludex/uvicorn/discussions/2706."
        )

    def get_loop_factory(self) -> Callable[[], asyncio.AbstractEventLoop] | None:
        """
        Resolves the configured event loop string into a concrete factory function.

        Returns:
            Callable[[], asyncio.AbstractEventLoop] | None: A factory function or None if no
                loop is needed.

        Raises:
            SystemExit: If a custom loop factory cannot be imported or is not callable.
        """
        from palfrey.importer import ImportFromStringError, _import_from_string

        if self.loop == "none":
            return None
        if self.loop == "auto":
            return _auto_loop_factory(use_subprocess=self.use_subprocess)
        if self.loop == "asyncio":
            return _asyncio_loop_factory(use_subprocess=self.use_subprocess)
        if self.loop == "uvloop":
            return _uvloop_loop_factory(use_subprocess=self.use_subprocess)

        try:
            loop_factory = _import_from_string(self.loop)
        except ImportFromStringError as exc:
            logger.error("Error loading custom loop setup function. %s", exc)
            raise SystemExit(1) from exc
        if not callable(loop_factory):
            logger.error("Error loading custom loop setup function. Import target not callable.")
            raise SystemExit(1)
        return cast("Callable[[], asyncio.AbstractEventLoop]", loop_factory)

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
        """
        Factory method to create a PalfreyConfig from an application import string.

        Args:
            app (str): The import string (e.g. 'my_module:app').
            host (str): Bind address.
            port (int): Bind port.
            app_dir (str | Path | None): Directory containing the app.
            **kwargs: Arbitrary configuration overrides.

        Returns:
            PalfreyConfig: An initialized configuration instance.
        """
        options: dict[str, Any] = {
            "app": app,
            "host": host,
            "port": port,
            "app_dir": str(app_dir) if app_dir is not None else None,
        }
        options.update(kwargs)
        return cls(**options)


# Alias for compatibility with older Uvicorn-based scripts
Config = PalfreyConfig
