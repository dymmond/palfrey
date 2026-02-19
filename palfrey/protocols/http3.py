from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from palfrey.protocols.http import HTTPRequest, HTTPResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from palfrey.config import PalfreyConfig
    from palfrey.types import ClientAddress, ServerAddress


_CONNECTION_SPECIFIC_HEADERS = {
    b"connection",
    b"keep-alive",
    b"proxy-connection",
    b"transfer-encoding",
    b"upgrade",
}


@dataclass(slots=True)
class _HTTP3StreamState:
    """
    In-memory representation of one HTTP/3 request stream.

    Attributes:
        method (str): Request method from pseudo-header `:method`.
        target (str): Request path+query from pseudo-header `:path`.
        headers (list[tuple[str, str]]): Non-pseudo request headers.
        body_chunks (list[bytes]): Body chunks received on the stream.
    """

    method: str
    target: str
    headers: list[tuple[str, str]]
    body_chunks: list[bytes] = field(default_factory=list)


def _to_text(value: bytes | str) -> str:
    """
    Decode header tokens to text with latin-1 compatibility.

    Args:
        value (bytes | str): Header name/value token.

    Returns:
        str: Decoded textual value.
    """
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return value


def _normalize_address(
    value: Any,
    *,
    default_host: str,
    default_port: int,
) -> tuple[str, int]:
    """
    Normalize transport endpoint metadata into a `(host, port)` tuple.

    Args:
        value (Any): Endpoint information from transport extra info.
        default_host (str): Host fallback.
        default_port (int): Port fallback.

    Returns:
        tuple[str, int]: Normalized endpoint.
    """
    if isinstance(value, tuple) and len(value) >= 2:
        host = str(value[0])
        try:
            port = int(value[1])
        except (TypeError, ValueError):
            port = default_port
        return host, port
    return default_host, default_port


def _decode_request_headers(
    headers: list[tuple[bytes | str, bytes | str]],
) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Parse HTTP/3 pseudo-headers and standard headers.

    Args:
        headers (list[tuple[bytes | str, bytes | str]]): Raw header block.

    Returns:
        tuple[str, str, list[tuple[str, str]]]: Parsed method, target, and regular headers.
    """
    method = "GET"
    target = "/"
    authority: str | None = None
    parsed_headers: list[tuple[str, str]] = []

    for raw_name, raw_value in headers:
        name = _to_text(raw_name)
        value = _to_text(raw_value)

        if name == ":method":
            method = value
        elif name == ":path":
            target = value or "/"
        elif name == ":authority":
            authority = value
        elif name.startswith(":"):
            continue
        else:
            parsed_headers.append((name, value))

    if authority and not any(name.lower() == "host" for name, _ in parsed_headers):
        parsed_headers.append(("host", authority))

    return method, target, parsed_headers


def _encode_response_headers(response: HTTPResponse) -> tuple[list[tuple[bytes, bytes]], bytes]:
    """
    Convert an HTTP response object into HTTP/3 response headers and payload.

    Args:
        response (HTTPResponse): Response state produced by ASGI handling.

    Returns:
        tuple[list[tuple[bytes, bytes]], bytes]: Header block and body payload.
    """
    body = b"" if response.suppress_body else b"".join(response.body_chunks)
    header_block: list[tuple[bytes, bytes]] = [
        (b":status", str(response.status).encode("ascii")),
    ]
    has_content_length = False

    for name, value in response.headers:
        normalized_name = name.lower()
        if normalized_name.startswith(b":") or normalized_name in _CONNECTION_SPECIFIC_HEADERS:
            continue
        if normalized_name == b"content-length":
            has_content_length = True
        header_block.append((normalized_name, value))

    if not has_content_length and not response.chunked_encoding:
        header_block.append((b"content-length", str(len(body)).encode("ascii")))

    return header_block, body


async def create_http3_server(
    *,
    config: PalfreyConfig,
    request_handler: Callable[[HTTPRequest, ClientAddress, ServerAddress], Awaitable[HTTPResponse]],
) -> Any:
    """
    Create and start an HTTP/3 QUIC listener.

    Args:
        config (PalfreyConfig): Runtime configuration.
        request_handler (Callable[[HTTPRequest, ClientAddress, ServerAddress], Awaitable[HTTPResponse]]):
            Coroutine that receives parsed HTTP/3 requests and returns a response.

    Returns:
        Any: The aioquic server object with `close()` and `wait_closed()` methods.

    Raises:
        RuntimeError: If required dependencies or TLS files are unavailable.
    """
    try:
        aioquic_asyncio = importlib.import_module("aioquic.asyncio")
        aioquic_asyncio_protocol = importlib.import_module("aioquic.asyncio.protocol")
        aioquic_h3_connection = importlib.import_module("aioquic.h3.connection")
        aioquic_h3_events = importlib.import_module("aioquic.h3.events")
        aioquic_quic_configuration = importlib.import_module("aioquic.quic.configuration")
        aioquic_quic_events = importlib.import_module("aioquic.quic.events")
    except ImportError as exc:
        raise RuntimeError("HTTP mode 'h3' requires the 'aioquic' package.") from exc

    serve = aioquic_asyncio.serve
    quic_connection_protocol_cls = aioquic_asyncio_protocol.QuicConnectionProtocol
    h3_alpn = aioquic_h3_connection.H3_ALPN
    h3_connection_cls = aioquic_h3_connection.H3Connection
    data_received_event = aioquic_h3_events.DataReceived
    headers_received_event = aioquic_h3_events.HeadersReceived
    quic_configuration_cls = aioquic_quic_configuration.QuicConfiguration
    protocol_negotiated_event = aioquic_quic_events.ProtocolNegotiated

    if not config.ssl_certfile:
        raise RuntimeError("HTTP mode 'h3' requires --ssl-certfile.")
    if not config.ssl_keyfile:
        raise RuntimeError("HTTP mode 'h3' requires --ssl-keyfile.")

    quic_configuration = quic_configuration_cls(is_client=False, alpn_protocols=h3_alpn)
    quic_configuration.load_cert_chain(
        certfile=config.ssl_certfile,
        keyfile=config.ssl_keyfile,
        password=config.ssl_keyfile_password,
    )

    class _PalfreyHTTP3Protocol(quic_connection_protocol_cls):
        """
        QUIC protocol adapter that translates HTTP/3 frames into ASGI requests.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._http: Any | None = None
            self._streams: dict[int, _HTTP3StreamState] = {}
            self._tasks: set[asyncio.Task[None]] = set()

        def connection_lost(self, exc: Exception | None) -> None:
            for task in list(self._tasks):
                task.cancel()
            super().connection_lost(exc)

        def quic_event_received(self, event: Any) -> None:
            if isinstance(event, protocol_negotiated_event) and event.alpn_protocol in h3_alpn:
                self._http = h3_connection_cls(self._quic)

            if self._http is None:
                return

            for http_event in self._http.handle_event(event):
                if isinstance(http_event, headers_received_event):
                    method, target, headers = _decode_request_headers(list(http_event.headers))
                    self._streams[http_event.stream_id] = _HTTP3StreamState(
                        method=method,
                        target=target,
                        headers=headers,
                    )
                    if http_event.stream_ended:
                        self._schedule_request(http_event.stream_id)
                elif isinstance(http_event, data_received_event):
                    stream_state = self._streams.get(http_event.stream_id)
                    if stream_state is not None:
                        stream_state.body_chunks.append(http_event.data)
                    if http_event.stream_ended:
                        self._schedule_request(http_event.stream_id)

            self.transmit()

        def _schedule_request(self, stream_id: int) -> None:
            task = asyncio.create_task(self._dispatch_request(stream_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        async def _dispatch_request(self, stream_id: int) -> None:
            if self._http is None:
                return

            stream_state = self._streams.pop(stream_id, None)
            if stream_state is None:
                return

            transport = getattr(self, "_transport", None)
            client = _normalize_address(
                transport.get_extra_info("peername") if transport is not None else None,
                default_host="0.0.0.0",
                default_port=0,
            )
            server = _normalize_address(
                transport.get_extra_info("sockname") if transport is not None else None,
                default_host=config.host,
                default_port=config.port,
            )

            body = b"".join(stream_state.body_chunks)
            request = HTTPRequest(
                method=stream_state.method,
                target=stream_state.target,
                http_version="HTTP/3",
                headers=stream_state.headers,
                body=body,
                body_chunks=stream_state.body_chunks or [b""],
            )

            try:
                response = await request_handler(request, client, server)
            except Exception:
                response = HTTPResponse(
                    status=500,
                    headers=[(b"content-type", b"text/plain")],
                    body_chunks=[b"Internal Server Error"],
                )

            headers, payload = _encode_response_headers(response)
            self._http.send_headers(stream_id=stream_id, headers=headers, end_stream=not payload)
            if payload:
                self._http.send_data(stream_id=stream_id, data=payload, end_stream=True)
            self.transmit()

    return await serve(
        config.host,
        config.port,
        configuration=quic_configuration,
        create_protocol=_PalfreyHTTP3Protocol,
    )
