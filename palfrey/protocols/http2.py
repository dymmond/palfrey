from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from palfrey.protocols.http import HTTPRequest, HTTPResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


_CONNECTION_SPECIFIC_HEADERS = {
    b"connection",
    b"keep-alive",
    b"proxy-connection",
    b"transfer-encoding",
    b"upgrade",
}


@dataclass(slots=True)
class _HTTP2StreamState:
    """
    Accumulates HTTP/2 request metadata and body fragments for one stream.

    Attributes:
        method (str): Request method from pseudo-header `:method`.
        target (str): Request target path+query from pseudo-header `:path`.
        headers (list[tuple[str, str]]): Non-pseudo request headers.
        body_chunks (list[bytes]): Buffered body payload chunks.
    """

    method: str
    target: str
    headers: list[tuple[str, str]]
    body_chunks: list[bytes] = field(default_factory=list)


def _to_text(value: bytes | str) -> str:
    """
    Normalize a header token into text using latin-1 decoding semantics.

    Args:
        value (bytes | str): Header name or value.

    Returns:
        str: Decoded string value.
    """
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return value


def _decode_request_headers(
    headers: list[tuple[bytes | str, bytes | str]],
) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Extract pseudo-headers and regular headers from an HTTP/2 header block.

    Args:
        headers (list[tuple[bytes | str, bytes | str]]): Raw event header list.

    Returns:
        tuple[str, str, list[tuple[str, str]]]: Parsed method, target, and standard headers.
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
    Convert an HTTP response object into HTTP/2-compliant headers and body bytes.

    Args:
        response (HTTPResponse): ASGI response accumulator.

    Returns:
        tuple[list[tuple[bytes, bytes]], bytes]: Header block and payload bytes.
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


async def _send_h2_response(
    *,
    connection: Any,
    writer: asyncio.StreamWriter,
    stream_id: int,
    response: HTTPResponse,
) -> None:
    """
    Send an HTTP/2 response on a specific stream.

    Args:
        connection (Any): `h2.connection.H2Connection` instance.
        writer (asyncio.StreamWriter): Stream writer for outbound bytes.
        stream_id (int): HTTP/2 stream identifier.
        response (HTTPResponse): Response to serialize.
    """
    headers, body = _encode_response_headers(response)
    end_stream = len(body) == 0
    connection.send_headers(stream_id=stream_id, headers=headers, end_stream=end_stream)

    if body:
        max_frame_size = int(getattr(connection, "max_outbound_frame_size", 16_384))
        offset = 0
        length = len(body)
        while offset < length:
            chunk = body[offset : offset + max_frame_size]
            offset += len(chunk)
            connection.send_data(stream_id, chunk, end_stream=offset >= length)

    payload = connection.data_to_send()
    if payload:
        writer.write(payload)
        await writer.drain()


async def serve_http2_connection(
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    request_handler: Callable[[HTTPRequest], Awaitable[HTTPResponse]],
) -> None:
    """
    Run an HTTP/2 connection loop and dispatch completed streams to an ASGI request handler.

    Args:
        reader (asyncio.StreamReader): Source stream reader.
        writer (asyncio.StreamWriter): Destination stream writer.
        request_handler (Callable[[HTTPRequest], Awaitable[HTTPResponse]]):
            Coroutine that receives parsed requests and returns a response.

    Raises:
        RuntimeError: If the `h2` dependency is not installed.
    """
    try:
        h2_config = importlib.import_module("h2.config")
        h2_connection = importlib.import_module("h2.connection")
        h2_events = importlib.import_module("h2.events")
        h2_exceptions = importlib.import_module("h2.exceptions")
    except ImportError as exc:
        raise RuntimeError("HTTP mode 'h2' requires the 'h2' package.") from exc

    h2_configuration_cls = h2_config.H2Configuration
    h2_connection_cls = h2_connection.H2Connection
    data_received_event = h2_events.DataReceived
    request_received_event = h2_events.RequestReceived
    stream_ended_event = h2_events.StreamEnded
    stream_reset_event = h2_events.StreamReset
    h2_error_cls = h2_exceptions.H2Error

    connection = h2_connection_cls(
        config=h2_configuration_cls(client_side=False, header_encoding=None)
    )
    streams: dict[int, _HTTP2StreamState] = {}

    connection.initiate_connection()
    writer.write(connection.data_to_send())
    await writer.drain()

    async def process_stream(stream_id: int) -> None:
        stream_state = streams.pop(stream_id, None)
        if stream_state is None:
            return

        body = b"".join(stream_state.body_chunks)
        request = HTTPRequest(
            method=stream_state.method,
            target=stream_state.target,
            http_version="HTTP/2",
            headers=stream_state.headers,
            body=body,
            body_chunks=stream_state.body_chunks or [b""],
        )
        response = await request_handler(request)
        await _send_h2_response(
            connection=connection,
            writer=writer,
            stream_id=stream_id,
            response=response,
        )

    while not writer.is_closing():
        incoming = await reader.read(65_536)
        if not incoming:
            break

        try:
            events = connection.receive_data(incoming)
        except h2_error_cls:
            connection.close_connection()
            writer.write(connection.data_to_send())
            await writer.drain()
            return

        for event in events:
            if isinstance(event, request_received_event):
                method, target, headers = _decode_request_headers(list(event.headers))
                streams[event.stream_id] = _HTTP2StreamState(
                    method=method,
                    target=target,
                    headers=headers,
                )
                if getattr(event, "stream_ended", False):
                    await process_stream(event.stream_id)
            elif isinstance(event, data_received_event):
                stream_state = streams.get(event.stream_id)
                if stream_state is not None:
                    stream_state.body_chunks.append(event.data)
                connection.acknowledge_received_data(
                    event.flow_controlled_length,
                    event.stream_id,
                )
                if getattr(event, "stream_ended", False):
                    await process_stream(event.stream_id)
            elif isinstance(event, stream_ended_event):
                await process_stream(event.stream_id)
            elif isinstance(event, stream_reset_event):
                streams.pop(event.stream_id, None)

        outbound = connection.data_to_send()
        if outbound:
            writer.write(outbound)
            await writer.drain()
