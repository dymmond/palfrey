"""Core async server implementation for Palfrey."""

from __future__ import annotations

import asyncio
import contextlib
import os
import random
import signal
import socket
import ssl
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from email.utils import formatdate
from importlib.util import find_spec
from types import FrameType
from typing import Any, cast

from palfrey.config import PalfreyConfig, create_ssl_context
from palfrey.importer import ResolvedApp, resolve_application as _resolve_application
from palfrey.lifespan import LifespanManager
from palfrey.logging_config import configure_logging, get_logger
from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    append_default_response_headers,
    build_http_scope,
    encode_http_response,
    is_websocket_upgrade,
    read_http_request,
    requires_100_continue,
    run_http_asgi,
    should_keep_alive,
)
from palfrey.protocols.utils import get_path_with_query_string
from palfrey.protocols.websocket import handle_websocket
from palfrey.types import ClientAddress, ServerAddress

logger = get_logger("palfrey.server")
access_logger = get_logger("palfrey.access")
PIPELINE_QUEUE_LIMIT = 16
# Compatibility alias retained for tests and monkeypatch-based integrations.
resolve_application = _resolve_application


HANDLED_SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)
if os.name == "nt":  # pragma: py-not-win32
    HANDLED_SIGNALS += (signal.SIGBREAK,)


@dataclass(slots=True)
class ConnectionContext:
    """Connection metadata used while processing one TCP stream."""

    client: ClientAddress
    server: ServerAddress
    is_tls: bool
    on_100_continue: Callable[[], Awaitable[None]] | None = None


@dataclass(slots=True, eq=False)
class _TrackedConnection:
    """Connection wrapper that exposes ``shutdown`` for graceful stop handling."""

    writer: asyncio.StreamWriter

    def shutdown(self) -> None:
        """Close the underlying writer to stop new request processing."""

        self.writer.close()


@dataclass(slots=True)
class _QueuedRequest:
    """Represents one parsed request or a terminal read outcome."""

    request: HTTPRequest | None = None
    error: Exception | None = None


@dataclass(slots=True)
class ServerState:
    """Shared server state container, compatible with Uvicorn concepts."""

    total_requests: int = 0
    connections: set[Any] = field(default_factory=set)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    default_headers: list[tuple[bytes, bytes]] = field(default_factory=list)


@dataclass(slots=True)
class PalfreyServer:
    """Run an ASGI application using Palfrey protocol and supervision layers."""

    config: PalfreyConfig
    server_state: ServerState = field(default_factory=ServerState)
    _resolved_app: ResolvedApp | None = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _active_requests: int = 0
    _server: asyncio.Server | None = None
    _servers: list[asyncio.Server] = field(default_factory=list)
    _external_sockets: list[socket.socket] = field(default_factory=list)
    _lifespan: LifespanManager | None = None
    _request_counter_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _max_requests_before_exit: int | None = None
    _base_default_headers: list[tuple[bytes, bytes]] = field(default_factory=list)
    _last_notified: float = 0.0
    _force_exit: bool = False
    _started: bool = False
    _captured_signals: list[int] = field(default_factory=list)

    @property
    def started(self) -> bool:
        """Return whether the server reached listening state."""

        return self._started or self._server is not None

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        """Start server, run until shutdown, and gracefully clean up resources."""

        with self.capture_signals():
            await self._serve(sockets=sockets)

    async def _serve(self, sockets: list[socket.socket] | None = None) -> None:
        """Start server, run until shutdown, and gracefully clean up resources."""

        configure_logging(self.config)
        self._validate_protocol_backends()
        if not self.config.loaded:
            self.config.load()

        self._resolved_app = ResolvedApp(
            app=self.config.loaded_app,
            interface=self.config.interface,
        )
        self._max_requests_before_exit = self._compute_max_requests_before_exit()
        self._base_default_headers = self._build_static_default_headers()

        if self.config.lifespan_class is not None:
            self._lifespan = self.config.lifespan_class(
                self._resolved_app.app,
                lifespan_mode=self.config.lifespan,
            )
            try:
                await self._lifespan.startup()
            except RuntimeError as exc:
                logger.error("Application startup failed: %s", exc)
                return
            if self._lifespan.should_exit:
                return

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, lambda _sig=sig: self._handle_exit_signal(_sig))

        ssl_context = self._build_ssl_context()
        use_protocol_factory = self._use_protocol_factory_mode()
        protocol_factory = self._build_protocol_factory(loop) if use_protocol_factory else None
        self._external_sockets = list(sockets) if sockets is not None else []

        try:
            if sockets is not None:
                self._servers = []
                for sock in sockets:
                    if use_protocol_factory:
                        assert protocol_factory is not None
                        server = await loop.create_server(
                            protocol_factory,
                            sock=sock,
                            ssl=ssl_context,
                            backlog=self.config.backlog,
                        )
                    else:
                        server = await asyncio.start_server(
                            self._handle_connection,
                            sock=sock,
                            ssl=ssl_context,
                            backlog=self.config.backlog,
                        )
                    self._servers.append(server)
                self._server = self._servers[0] if self._servers else None
            elif self.config.fd is not None:
                server_socket = socket.fromfd(self.config.fd, socket.AF_UNIX, socket.SOCK_STREAM)
                server_socket.setblocking(False)
                if use_protocol_factory:
                    assert protocol_factory is not None
                    self._server = await loop.create_server(
                        protocol_factory,
                        sock=server_socket,
                        ssl=ssl_context,
                        backlog=self.config.backlog,
                    )
                else:
                    self._server = await asyncio.start_server(
                        self._handle_connection,
                        sock=server_socket,
                        ssl=ssl_context,
                        backlog=self.config.backlog,
                    )
            elif self.config.uds:
                uds_perms = 0o666
                if os.path.exists(self.config.uds):
                    uds_perms = os.stat(self.config.uds).st_mode
                if use_protocol_factory:
                    assert protocol_factory is not None
                    self._server = await loop.create_unix_server(
                        protocol_factory,
                        path=self.config.uds,
                        backlog=self.config.backlog,
                        ssl=ssl_context,
                    )
                else:
                    self._server = await asyncio.start_unix_server(
                        self._handle_connection,
                        path=self.config.uds,
                        backlog=self.config.backlog,
                        ssl=ssl_context,
                    )
                with contextlib.suppress(OSError):
                    os.chmod(self.config.uds, uds_perms)
            else:
                if use_protocol_factory:
                    assert protocol_factory is not None
                    self._server = await loop.create_server(
                        protocol_factory,
                        host=self.config.host,
                        port=self.config.port,
                        backlog=self.config.backlog,
                        ssl=ssl_context,
                        reuse_port=self.config.workers_count > 1,
                    )
                else:
                    self._server = await asyncio.start_server(
                        self._handle_connection,
                        host=self.config.host,
                        port=self.config.port,
                        backlog=self.config.backlog,
                        ssl=ssl_context,
                        reuse_port=self.config.workers_count > 1,
                    )
        except OSError as exc:
            logger.error("%s", exc)
            if self._lifespan is not None:
                await self._lifespan.shutdown()
            return

        if not self._servers:
            self._servers = [self._server] if self._server is not None else []

        listening_sockets: list[socket.socket] = []
        if sockets is None:
            for server in self._servers:
                bound_sockets = cast(list[socket.socket] | None, getattr(server, "sockets", None))
                if bound_sockets:
                    listening_sockets.extend(bound_sockets)

        for sock in listening_sockets:
            logger.info("Listening on %s", sock.getsockname())
        self._started = True

        await self._main_loop()
        await self._shutdown()

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        """Run server inside a fresh asyncio event loop."""
        asyncio.run(self.serve(sockets=sockets))

    def request_shutdown(self) -> None:
        """Trigger server shutdown from external coordinator code."""

        self._shutdown_event.set()

    def _handle_exit_signal(self, sig: signal.Signals) -> None:
        """Handle process signal semantics for graceful and forced exits."""

        if self._shutdown_event.is_set() and sig == signal.SIGINT:
            self._force_exit = True
            return
        self.request_shutdown()

    @contextlib.contextmanager
    def capture_signals(self):
        """Capture and restore process signal handlers around server runtime."""

        if threading.current_thread() is not threading.main_thread():
            yield
            return

        original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)

        for captured_signal in reversed(self._captured_signals):
            signal.raise_signal(captured_signal)

    def handle_exit(self, sig: int, _frame: FrameType | None) -> None:
        """Signal handler compatible with ``signal.signal`` callback shape."""

        self._captured_signals.append(sig)
        self._handle_exit_signal(signal.Signals(sig))

    async def _main_loop(self) -> None:
        """Run periodic server maintenance ticks until shutdown criteria are met."""

        counter = 0
        should_exit = await self._on_tick(counter)
        while not should_exit:
            counter = (counter + 1) % 864000
            await asyncio.sleep(0.1)
            should_exit = await self._on_tick(counter)

    async def _on_tick(self, counter: int) -> bool:
        """Run one server tick, mirroring Uvicorn's maintenance cadence."""

        if counter % 10 == 0:
            if not self._base_default_headers:
                self._base_default_headers = self._build_static_default_headers()
            current_time = time.time()
            current_date = formatdate(current_time, usegmt=True).encode("ascii")
            current_headers = list(self._base_default_headers)
            header_names = {name for name, _ in current_headers}
            if self.config.date_header and b"date" not in header_names:
                current_headers.insert(0, (b"date", current_date))
            self.server_state.default_headers = current_headers

            if (
                self.config.callback_notify is not None
                and current_time - self._last_notified > self.config.timeout_notify
            ):
                self._last_notified = current_time
                await self.config.callback_notify()

        if self._shutdown_event.is_set():
            return True

        if self._max_requests_before_exit is None:
            self._max_requests_before_exit = self._compute_max_requests_before_exit()
        if (
            self._max_requests_before_exit is not None
            and self.server_state.total_requests >= self._max_requests_before_exit
        ):
            logger.info(
                "Maximum request limit of %d exceeded. Terminating process.",
                self._max_requests_before_exit,
            )
            self.request_shutdown()
            return True

        return False

    async def _shutdown(self) -> None:
        """Perform graceful server shutdown with connection/task draining."""

        logger.info("Shutting down")

        servers = list(self._servers)
        if not servers and self._server is not None:
            servers = [self._server]

        for server in servers:
            server.close()
        for server in servers:
            await server.wait_closed()
        self._servers.clear()
        self._server = None

        for sock in self._external_sockets:
            with contextlib.suppress(OSError):
                sock.close()
        self._external_sockets.clear()

        for connection in list(self.server_state.connections):
            connection.shutdown()
        await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(
                self._wait_tasks_to_complete(),
                timeout=self.config.timeout_graceful_shutdown,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Cancel %s running task(s), timeout graceful shutdown exceeded",
                len(self.server_state.tasks),
            )
            for task in list(self.server_state.tasks):
                task.cancel(msg="Task cancelled, timeout graceful shutdown exceeded")

        if self._lifespan is not None and not self._force_exit:
            await self._lifespan.shutdown()

    async def _wait_tasks_to_complete(self) -> None:
        """Wait for active connections and in-flight tasks to drain."""

        if self.server_state.connections and not self._force_exit:
            logger.info("Waiting for connections to close. (CTRL+C to force quit)")
            while self.server_state.connections and not self._force_exit:
                await asyncio.sleep(0.1)

        if self.server_state.tasks and not self._force_exit:
            logger.info("Waiting for background tasks to complete. (CTRL+C to force quit)")
            while self.server_state.tasks and not self._force_exit:
                await asyncio.sleep(0.1)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._resolved_app is None:
            return

        peername = writer.get_extra_info("peername")
        sockname = writer.get_extra_info("sockname")
        ssl_object = writer.get_extra_info("ssl_object")

        client = self._normalize_address(
            peername,
            default_host="0.0.0.0",
            default_port=0,
        )
        server = self._normalize_address(
            sockname,
            default_host=self.config.host,
            default_port=self.config.port,
        )

        context = ConnectionContext(client=client, server=server, is_tls=ssl_object is not None)
        tracked_connection = _TrackedConnection(writer=writer)
        self.server_state.connections.add(tracked_connection)
        current_task = asyncio.current_task()
        if current_task is not None:
            self.server_state.tasks.add(current_task)

        keep_processing = True
        keep_alive_timeout = self.config.timeout_keep_alive
        request_queue: asyncio.Queue[_QueuedRequest] = asyncio.Queue(maxsize=PIPELINE_QUEUE_LIMIT)
        request_reader_task = asyncio.create_task(
            self._queue_connection_requests(
                reader=reader,
                queue=request_queue,
                keep_alive_timeout=keep_alive_timeout,
            )
        )

        async def stop_request_reader() -> None:
            if request_reader_task.done():
                return
            request_reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await request_reader_task

        try:
            while keep_processing:
                queued_request = await request_queue.get()
                if queued_request.error is not None:
                    raise queued_request.error

                request = queued_request.request
                if request is None:
                    break

                if is_websocket_upgrade(request):
                    await stop_request_reader()
                    if self.config.effective_ws == "none":
                        error_response = HTTPResponse(
                            status=400,
                            headers=[(b"content-type", b"text/plain")],
                            body_chunks=[b"Bad Request"],
                        )
                        await self._write_response(writer, error_response, keep_alive=False)
                        break

                    await handle_websocket(
                        self._resolved_app.app,
                        self.config,
                        reader=reader,
                        writer=writer,
                        headers=request.headers,
                        target=request.target,
                        client=context.client,
                        server=context.server,
                        is_tls=context.is_tls,
                    )
                    break

                if requires_100_continue(request):

                    async def send_continue() -> None:
                        writer.write(b"HTTP/1.1 100 Continue\r\n\r\n")
                        await writer.drain()

                    context.on_100_continue = send_continue
                else:
                    context.on_100_continue = None

                if self._is_concurrency_limit_exceeded():
                    await self._write_response(
                        writer,
                        self._service_unavailable_response(),
                        keep_alive=False,
                    )
                    break

                acquired = await self._enter_request_slot()
                if not acquired:
                    await self._write_response(
                        writer,
                        self._service_unavailable_response(),
                        keep_alive=False,
                    )
                    break

                try:
                    response = await self._handle_http_request(request, context)
                finally:
                    await self._leave_request_slot()
                keep_processing = should_keep_alive(request, response)

                await self._write_response(writer, response, keep_alive=keep_processing)

                self.server_state.total_requests += 1
                if self._max_requests_before_exit is None:
                    self._max_requests_before_exit = self._compute_max_requests_before_exit()
                if (
                    self._max_requests_before_exit is not None
                    and self.server_state.total_requests >= self._max_requests_before_exit
                ):
                    self.request_shutdown()
        except ValueError as exc:
            logger.warning("Bad request: %s", exc)
            error_response = HTTPResponse(status=400, headers=[(b"content-type", b"text/plain")])
            error_response.body_chunks = [b"Bad Request"]
            await self._write_response(writer, error_response, keep_alive=False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Connection handler failed: %s", exc)
            error_response = HTTPResponse(status=500, headers=[(b"content-type", b"text/plain")])
            error_response.body_chunks = [b"Internal Server Error"]
            await self._write_response(writer, error_response, keep_alive=False)
        finally:
            await stop_request_reader()
            self.server_state.connections.discard(tracked_connection)
            if current_task is not None:
                self.server_state.tasks.discard(current_task)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _queue_connection_requests(
        self,
        *,
        reader: asyncio.StreamReader,
        queue: asyncio.Queue[_QueuedRequest],
        keep_alive_timeout: float,
    ) -> None:
        """Read requests continuously and enqueue them for pipelined processing."""

        first_request = True
        try:
            while True:
                request_coro = read_http_request(
                    reader,
                    max_head_size=self.config.h11_max_incomplete_event_size or 1_048_576,
                    parser_mode=self.config.effective_http,
                )
                try:
                    if first_request and keep_alive_timeout > 0:
                        request = await request_coro
                    else:
                        request = await asyncio.wait_for(
                            request_coro,
                            timeout=keep_alive_timeout,
                        )
                except asyncio.TimeoutError:
                    await self._queue_with_backpressure(reader, queue, _QueuedRequest(request=None))
                    return
                except Exception as exc:  # noqa: BLE001
                    await self._queue_with_backpressure(reader, queue, _QueuedRequest(error=exc))
                    return

                first_request = False
                await self._queue_with_backpressure(reader, queue, _QueuedRequest(request=request))
                if request is None:
                    return
        except asyncio.CancelledError:
            return

    async def _queue_with_backpressure(
        self,
        reader: asyncio.StreamReader,
        queue: asyncio.Queue[_QueuedRequest],
        item: _QueuedRequest,
    ) -> None:
        """Queue an item while pausing reads when request pipeline is saturated."""

        paused = False
        if queue.full():
            self._pause_stream_reader(reader)
            paused = True
        try:
            await queue.put(item)
        finally:
            if paused:
                self._resume_stream_reader(reader)

    @staticmethod
    def _pause_stream_reader(reader: asyncio.StreamReader) -> None:
        """Pause socket reads for a stream reader transport when available."""

        transport = getattr(reader, "_transport", None)
        if transport is None:
            return
        with contextlib.suppress(Exception):
            transport.pause_reading()

    @staticmethod
    def _resume_stream_reader(reader: asyncio.StreamReader) -> None:
        """Resume socket reads for a stream reader transport when available."""

        transport = getattr(reader, "_transport", None)
        if transport is None:
            return
        with contextlib.suppress(Exception):
            transport.resume_reading()

    async def _handle_http_request(
        self,
        request: HTTPRequest,
        context: ConnectionContext,
    ) -> HTTPResponse:
        if self._resolved_app is None:
            raise RuntimeError("Application is not resolved.")

        scope = build_http_scope(
            request,
            client=context.client,
            server=context.server,
            root_path=self.config.root_path,
            is_tls=context.is_tls,
        )

        body_input: bytes | list[bytes] = (
            request.body_chunks if request.body_chunks else request.body
        )
        response = await run_http_asgi(
            self._resolved_app.app,
            scope,
            body_input,
            expect_100_continue=requires_100_continue(request),
            on_100_continue=context.on_100_continue,
        )
        default_headers = self.server_state.default_headers or None
        append_default_response_headers(
            response,
            self.config,
            default_headers=default_headers,
        )

        if self.config.access_log:
            request_path = get_path_with_query_string(scope)
            access_logger.info(
                '%s - "%s %s HTTP/%s" %s',
                scope["client"][0],
                scope["method"],
                request_path,
                scope["http_version"],
                response.status,
            )

        return response

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        response: HTTPResponse,
        *,
        keep_alive: bool,
    ) -> None:
        payload = encode_http_response(response, keep_alive=keep_alive)
        writer.write(payload)
        await writer.drain()

    def _service_unavailable_response(self) -> HTTPResponse:
        response = HTTPResponse(status=503, headers=[(b"content-type", b"text/plain")])
        response.body_chunks = [b"Service Unavailable"]
        append_default_response_headers(response, self.config)
        return response

    async def _enter_request_slot(self) -> bool:
        """Attempt to reserve request-processing capacity."""

        limit = self.config.limit_concurrency
        if limit is None:
            return True

        async with self._request_counter_lock:
            if self._active_requests >= limit:
                return False
            self._active_requests += 1
            return True

    def _is_concurrency_limit_exceeded(self) -> bool:
        """Return whether current connection/task counts exceed configured limit."""

        limit = self.config.limit_concurrency
        if limit is None:
            return False
        return len(self.server_state.connections) >= limit or len(self.server_state.tasks) >= limit

    async def _leave_request_slot(self) -> None:
        """Release request-processing capacity token."""

        limit = self.config.limit_concurrency
        if limit is None:
            return

        async with self._request_counter_lock:
            if self._active_requests > 0:
                self._active_requests -= 1

    @staticmethod
    def _normalize_address(
        value: Any,
        *,
        default_host: str,
        default_port: int,
    ) -> tuple[str, int]:
        if isinstance(value, tuple) and len(value) >= 2:
            host = str(value[0])
            try:
                port = int(value[1])
            except (TypeError, ValueError):
                port = default_port
            return host, port
        return default_host, default_port

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        if self.config.ssl_context is not None:
            return self.config.ssl_context
        if not self.config.is_ssl:
            return None

        assert self.config.ssl_certfile
        self.config.ssl_context = create_ssl_context(
            certfile=self.config.ssl_certfile,
            keyfile=self.config.ssl_keyfile,
            password=self.config.ssl_keyfile_password,
            ssl_version=self.config.ssl_version,
            cert_reqs=self.config.ssl_cert_reqs,
            ca_certs=self.config.ssl_ca_certs,
            ciphers=self.config.ssl_ciphers,
        )
        return self.config.ssl_context

    def _compute_max_requests_before_exit(self) -> int | None:
        """Compute effective max requests, including configured jitter."""

        if self.config.limit_max_requests is None:
            return None

        return self.config.limit_max_requests + random.randint(
            0,
            self.config.limit_max_requests_jitter,
        )

    def _build_static_default_headers(self) -> list[tuple[bytes, bytes]]:
        """Build configured default response headers excluding dynamic date."""

        encoded_headers = list(getattr(self.config, "encoded_headers", []))
        if encoded_headers:
            return encoded_headers

        configured_headers = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in self.config.normalized_headers
        ]
        configured_names = {name for name, _ in configured_headers}
        if self.config.server_header and b"server" not in configured_names:
            return [(b"server", b"palfrey"), *configured_headers]
        return configured_headers

    def _use_protocol_factory_mode(self) -> bool:
        """Return whether runtime should delegate I/O to protocol-class factory."""

        protocol_class = self.config.http_protocol_class
        return isinstance(protocol_class, type) and issubclass(protocol_class, asyncio.Protocol)

    def _build_protocol_factory(
        self, loop: asyncio.AbstractEventLoop
    ) -> Callable[[], asyncio.Protocol]:
        """Build protocol factory callable for custom protocol-class execution."""

        protocol_class = cast(type[asyncio.Protocol], self.config.http_protocol_class)
        protocol_constructor = cast("Callable[..., asyncio.Protocol]", protocol_class)
        app_state = getattr(self._lifespan, "state", {}) if self._lifespan is not None else {}

        def create_protocol(
            _loop: asyncio.AbstractEventLoop | None = None,
        ) -> asyncio.Protocol:
            return protocol_constructor(
                config=self.config,
                server_state=self.server_state,
                app_state=app_state,
                _loop=_loop or loop,
            )

        return create_protocol

    def _validate_protocol_backends(self) -> None:
        """Validate that selected protocol backend dependencies are importable.

        Raises:
            RuntimeError: If an explicitly selected backend is unavailable.
        """

        if self.config.http == "httptools" and find_spec("httptools") is None:
            raise RuntimeError("HTTP mode 'httptools' requires the 'httptools' package.")

        selected_ws = self.config.effective_ws
        if selected_ws == "none":
            return

        if selected_ws in {"websockets", "websockets-sansio"} and find_spec("websockets") is None:
            raise RuntimeError(f"WebSocket mode '{selected_ws}' requires the 'websockets' package.")

        if selected_ws == "wsproto" and find_spec("wsproto") is None:
            raise RuntimeError("WebSocket mode 'wsproto' requires the 'wsproto' package.")


Server = PalfreyServer
