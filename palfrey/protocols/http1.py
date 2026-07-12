"""Opt-in low-level HTTP/1 protocol for performance validation slices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from typing import TYPE_CHECKING, Any, cast

from palfrey.acceleration import parse_request_head_normalized
from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    append_default_response_headers,
    build_http_scope,
    encode_http_response,
    requires_100_continue,
    run_http_asgi,
    should_keep_alive,
)

if TYPE_CHECKING:
    from palfrey.config import PalfreyConfig
    from palfrey.server import ServerState
    from palfrey.types import ASGIApplication, ClientAddress, ServerAddress

logger = logging.getLogger("palfrey.server")

_HEAD_SEPARATOR = b"\r\n\r\n"
_MAX_HEAD_SIZE = 1_048_576
_MAX_BODY_SIZE = 4_194_304


class PalfreyHTTPProtocol(asyncio.Protocol):
    """Low-level HTTP/1 protocol behind explicit opt-in configuration.

    This class is intentionally narrow for now: it provides a measurable protocol
    baseline without replacing the stream-based compatibility path.
    """

    def __init__(
        self,
        *,
        config: PalfreyConfig,
        server_state: ServerState,
        app_state: dict[str, Any] | None = None,
        _loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.config = config
        self.server_state = server_state
        self.app_state = app_state or {}
        self.loop = _loop or asyncio.get_event_loop()
        self.transport: asyncio.Transport | None = None
        self.buffer = bytearray()
        self.active_task: asyncio.Task[None] | None = None
        self.keep_alive_handle: asyncio.TimerHandle | None = None
        self.client: ClientAddress = ("0.0.0.0", 0)
        self.server: ServerAddress = (self.config.host, self.config.port)
        self.is_tls = False
        self.max_requests_before_exit = self.config.limit_max_requests
        if self.max_requests_before_exit is not None and self.config.limit_max_requests_jitter > 0:
            # Keep the protocol slice deterministic; jitter remains handled by the default server path.
            self.max_requests_before_exit += 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.Transport, transport)
        sock = self.transport.get_extra_info("socket")
        if sock is not None and hasattr(socket, "TCP_NODELAY"):
            with contextlib.suppress(OSError, AttributeError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        self.client = _normalize_address(
            self.transport.get_extra_info("peername"),
            default_host="0.0.0.0",
            default_port=0,
        )
        self.server = _normalize_address(
            self.transport.get_extra_info("sockname"),
            default_host=self.config.host,
            default_port=self.config.port,
        )
        self.is_tls = self.transport.get_extra_info("ssl_object") is not None
        self.server_state.connections.add(self)

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_keep_alive_timeout()
        self.server_state.connections.discard(self)
        if self.active_task is not None:
            self.active_task.cancel()
            self.server_state.tasks.discard(self.active_task)
            self.active_task = None
        self.transport = None

    def data_received(self, data: bytes) -> None:
        self._cancel_keep_alive_timeout()
        self.buffer.extend(data)
        self._parse_available_requests()

    def eof_received(self) -> bool | None:
        return None

    def _parse_available_requests(self) -> None:
        if self.transport is None or self.transport.is_closing() or self.active_task is not None:
            return

        if self.buffer:
            self._cancel_keep_alive_timeout()

        parsed = self._pop_request()
        if parsed is None:
            return

        request, error_response = parsed
        if error_response is not None:
            self._write_response(error_response, keep_alive=False)
            self._close_transport()
            return

        if request is None:
            return

        if self._is_concurrency_limit_exceeded():
            response = HTTPResponse(
                status=503,
                headers=[(b"content-type", b"text/plain")],
                body_chunks=[b"Service Unavailable"],
            )
            append_default_response_headers(response, self.config)
            self._write_response(response, keep_alive=False)
            self._close_transport()
            return

        self.active_task = self.loop.create_task(self._run_request(request))
        self.active_task.add_done_callback(self._request_done)
        self.server_state.tasks.add(self.active_task)

    def _pop_request(self) -> tuple[HTTPRequest | None, HTTPResponse | None] | None:
        separator_index = self.buffer.find(_HEAD_SEPARATOR)
        if separator_index < 0:
            if len(self.buffer) > _MAX_HEAD_SIZE:
                return None, _plain_response(400, b"Bad Request")
            return None

        head_end = separator_index + len(_HEAD_SEPARATOR)
        if head_end > _MAX_HEAD_SIZE:
            return None, _plain_response(400, b"Bad Request")

        head = bytes(self.buffer[:head_end])
        try:
            (
                method_raw,
                target_raw,
                version_raw,
                headers,
                content_length_raw,
                transfer_encoding,
                connection_header,
                expect_header,
                websocket_upgrade,
            ) = parse_request_head_normalized(head)
        except ValueError:
            return None, _plain_response(400, b"Bad Request")

        if websocket_upgrade:
            return None, _plain_response(400, b"Bad Request")
        if b"chunked" in transfer_encoding:
            return None, _plain_response(501, b"Not Implemented")

        content_length = 0
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except ValueError:
                return None, _plain_response(400, b"Bad Request")
            if content_length < 0 or content_length > _MAX_BODY_SIZE:
                return None, _plain_response(400, b"Bad Request")

        request_end = head_end + content_length
        if len(self.buffer) < request_end:
            return None

        body = bytes(self.buffer[head_end:request_end])
        del self.buffer[:request_end]
        request = HTTPRequest(
            method=method_raw.decode("latin-1"),
            target=target_raw.decode("latin-1"),
            http_version=version_raw.decode("latin-1"),
            headers=headers,
            body=body,
            body_chunks=[body] if body else [],
            headers_normalized=True,
            connection_header=connection_header,
            expect_header=expect_header,
            is_websocket_upgrade=False,
        )
        return request, None

    async def _run_request(self, request: HTTPRequest) -> None:
        if self.transport is None or self.transport.is_closing():
            return

        app = cast("ASGIApplication", self.config.loaded_app)
        scope = build_http_scope(
            request,
            client=self.client,
            server=self.server,
            root_path=self.config.root_path,
            is_tls=self.is_tls,
            app_state=self.app_state,
            asgi_version="2.0" if self.config.interface == "asgi2" else "3.0",
        )

        async def send_continue() -> None:
            if self.transport is not None and not self.transport.is_closing():
                self.transport.write(b"HTTP/1.1 100 Continue\r\n\r\n")

        response = await run_http_asgi(
            app,
            scope,
            request.body_chunks if request.body_chunks else request.body,
            expect_100_continue=requires_100_continue(request),
            on_100_continue=send_continue,
        )
        append_default_response_headers(
            response,
            self.config,
            default_headers=self.server_state.default_headers or None,
        )
        keep_alive = should_keep_alive(request, response)
        self._write_response(response, keep_alive=keep_alive)
        self.server_state.total_requests += 1

        if not keep_alive or self._request_limit_reached():
            self._close_transport()
            return

        self._arm_keep_alive_timeout()

    def _request_done(self, task: asyncio.Task[None]) -> None:
        self.server_state.tasks.discard(task)
        if self.active_task is task:
            self.active_task = None
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                logger.exception("HTTP protocol request failed: %s", exc)
                self._close_transport()
                return
        self._parse_available_requests()

    def _write_response(self, response: HTTPResponse, *, keep_alive: bool) -> None:
        if self.transport is None or self.transport.is_closing():
            return
        self.transport.write(encode_http_response(response, keep_alive=keep_alive))

    def _arm_keep_alive_timeout(self) -> None:
        self._cancel_keep_alive_timeout()
        if self.config.timeout_keep_alive <= 0:
            self._close_transport()
            return
        self.keep_alive_handle = self.loop.call_later(
            self.config.timeout_keep_alive,
            self._close_transport,
        )

    def _cancel_keep_alive_timeout(self) -> None:
        if self.keep_alive_handle is not None:
            self.keep_alive_handle.cancel()
            self.keep_alive_handle = None

    def _close_transport(self) -> None:
        if self.transport is not None and not self.transport.is_closing():
            self.transport.close()

    def _is_concurrency_limit_exceeded(self) -> bool:
        limit = self.config.limit_concurrency
        if limit is None:
            return False
        return len(self.server_state.connections) >= limit or len(self.server_state.tasks) >= limit

    def _request_limit_reached(self) -> bool:
        return (
            self.max_requests_before_exit is not None
            and self.server_state.total_requests >= self.max_requests_before_exit
        )


def _plain_response(status: int, body: bytes) -> HTTPResponse:
    return HTTPResponse(
        status=status,
        headers=[(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())],
        body_chunks=[body],
    )


def _normalize_address(
    value: Any,
    *,
    default_host: str,
    default_port: int,
) -> tuple[str, int]:
    if isinstance(value, tuple) and len(value) >= 2:
        return str(value[0]), int(value[1] or 0)
    return default_host, default_port
