"""Core async server implementation for Palfrey."""

from __future__ import annotations

import asyncio
import contextlib
import random
import signal
import socket
import ssl
from dataclasses import dataclass, field
from typing import Any, cast

from palfrey.config import PalfreyConfig
from palfrey.importer import ResolvedApp, resolve_application
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


@dataclass(slots=True)
class ConnectionContext:
    """Connection metadata used while processing one TCP stream."""

    client: ClientAddress
    server: ServerAddress
    is_tls: bool


@dataclass(slots=True)
class PalfreyServer:
    """Run an ASGI application using Palfrey protocol and supervision layers."""

    config: PalfreyConfig
    _resolved_app: ResolvedApp | None = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _requests_processed: int = 0
    _active_requests: int = 0
    _server: asyncio.AbstractServer | None = None
    _lifespan: LifespanManager | None = None
    _request_counter_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _max_requests_before_exit: int | None = None

    @property
    def started(self) -> bool:
        """Return whether the server socket is currently accepting connections."""

        return self._server is not None

    async def serve(self) -> None:
        """Start server, run until shutdown, and gracefully clean up resources."""

        configure_logging(self.config)
        self._resolved_app = resolve_application(self.config)
        self._max_requests_before_exit = self._compute_max_requests_before_exit()

        if self.config.lifespan != "off":
            self._lifespan = LifespanManager(self._resolved_app.app)
            await self._lifespan.startup()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self._shutdown_event.set)

        ssl_context = self._build_ssl_context()

        if self.config.fd is not None:
            server_socket = socket.fromfd(self.config.fd, socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setblocking(False)
            self._server = await asyncio.start_server(
                self._handle_connection,
                sock=server_socket,
                ssl=ssl_context,
                backlog=self.config.backlog,
            )
        elif self.config.uds:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=self.config.uds,
                backlog=self.config.backlog,
                ssl=ssl_context,
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

        sockets = self._server.sockets or []
        for sock in sockets:
            logger.info("Listening on %s", sock.getsockname())

        await self._shutdown_event.wait()

        self._server.close()
        await self._server.wait_closed()

        if self._lifespan is not None:
            await self._lifespan.shutdown()

    def run(self) -> None:
        """Run server inside a fresh asyncio event loop."""
        asyncio.run(self.serve())

    def request_shutdown(self) -> None:
        """Trigger server shutdown from external coordinator code."""

        self._shutdown_event.set()

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

        keep_processing = True

        try:
            while keep_processing:
                try:
                    request = await asyncio.wait_for(
                        read_http_request(
                            reader,
                            max_head_size=self.config.h11_max_incomplete_event_size or 1_048_576,
                        ),
                        timeout=self.config.timeout_keep_alive,
                    )
                except asyncio.TimeoutError:
                    break
                if request is None:
                    break

                if self.config.ws != "none" and is_websocket_upgrade(request):
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
                    writer.write(b"HTTP/1.1 100 Continue\r\n\r\n")
                    await writer.drain()

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

                self._requests_processed += 1
                if self._max_requests_before_exit is None:
                    self._max_requests_before_exit = self._compute_max_requests_before_exit()
                if (
                    self._max_requests_before_exit is not None
                    and self._requests_processed >= self._max_requests_before_exit
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
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

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

        response = await run_http_asgi(self._resolved_app.app, scope, request.body)
        append_default_response_headers(response, self.config)

        if self.config.access_log:
            request_path = get_path_with_query_string(scope)
            logger.info(
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
        if not self.config.ssl_certfile:
            return None

        ssl_version = self.config.ssl_version or ssl.PROTOCOL_TLS_SERVER
        context = ssl.SSLContext(ssl_version)
        context.load_cert_chain(
            certfile=self.config.ssl_certfile,
            keyfile=self.config.ssl_keyfile,
            password=self.config.ssl_keyfile_password,
        )

        if self.config.ssl_ca_certs:
            context.load_verify_locations(self.config.ssl_ca_certs)

        if self.config.ssl_cert_reqs is not None:
            context.verify_mode = cast(ssl.VerifyMode, self.config.ssl_cert_reqs)

        context.set_ciphers(self.config.ssl_ciphers)
        return context

    def _compute_max_requests_before_exit(self) -> int | None:
        """Compute effective max requests, including configured jitter."""

        if self.config.limit_max_requests is None:
            return None

        return self.config.limit_max_requests + random.randint(
            0,
            self.config.limit_max_requests_jitter,
        )
