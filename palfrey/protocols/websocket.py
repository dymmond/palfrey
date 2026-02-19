"""WebSocket protocol support for Palfrey."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import importlib
import struct
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any, cast
from urllib.parse import unquote

from palfrey.acceleration import unmask_websocket_payload
from palfrey.config import PalfreyConfig
from palfrey.http_date import cached_http_date_header
from palfrey.types import ASGIApplication, ClientAddress, Message, Scope, ServerAddress

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass(slots=True)
class WebSocketFrame:
    """Decoded WebSocket frame payload."""

    fin: bool
    opcode: int
    payload: bytes


def _header_value(headers: list[tuple[str, str]], key: str) -> str | None:
    lookup = key.lower()
    for name, value in headers:
        if name.lower() == lookup:
            return value
    return None


def _header_map(headers: list[tuple[str, str]]) -> dict[str, str]:
    """Build case-insensitive string header lookup map."""

    mapped: dict[str, str] = {}
    for name, value in headers:
        mapped[name.lower()] = value
    return mapped


def build_websocket_scope(
    *,
    target: str,
    headers: list[tuple[str, str]],
    client: ClientAddress,
    server: ServerAddress,
    root_path: str,
    is_tls: bool,
    protocol_header: str | None = None,
) -> Scope:
    """Build an ASGI websocket scope."""

    path, _, query = target.partition("?")
    decoded_path = unquote(path)
    raw_path = path.encode("latin-1")
    root_path_bytes = root_path.encode("latin-1")
    full_path = root_path + decoded_path
    full_raw_path = root_path_bytes + raw_path

    if protocol_header is None:
        protocol_header = _header_value(headers, "sec-websocket-protocol")
    subprotocols = []
    if protocol_header:
        subprotocols = [item.strip() for item in protocol_header.split(",") if item.strip()]

    return {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "wss" if is_tls else "ws",
        "path": full_path,
        "raw_path": full_raw_path,
        "query_string": query.encode("latin-1"),
        "root_path": root_path,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in headers
        ],
        "client": client,
        "server": server,
        "subprotocols": subprotocols,
        "state": {},
        "extensions": {"websocket.http.response": {}},
    }


def _accept_value(client_key: str) -> str:
    token = (client_key + _WS_GUID).encode("latin-1")
    digest = hashlib.sha1(token, usedforsecurity=False).digest()
    return base64.b64encode(digest).decode("ascii")


def _build_handshake_response_for_key(
    client_key: str,
    *,
    subprotocol: str | None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> bytes:
    """Create HTTP 101 response bytes from pre-resolved client key."""

    response_headers = [
        b"HTTP/1.1 101 Switching Protocols",
        b"upgrade: websocket",
        b"connection: Upgrade",
        b"sec-websocket-accept: " + _accept_value(client_key).encode("ascii"),
    ]

    if subprotocol:
        response_headers.append(b"sec-websocket-protocol: " + subprotocol.encode("latin-1"))

    for name, value in extra_headers or []:
        response_headers.append(name + b": " + value)

    return b"\r\n".join(response_headers) + b"\r\n\r\n"


def _http_date_header() -> bytes:
    return cached_http_date_header()


def _default_websocket_headers(config: PalfreyConfig) -> list[tuple[bytes, bytes]]:
    configured_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in config.normalized_headers
    ]
    configured_names = {name for name, _ in configured_headers}

    default_headers: list[tuple[bytes, bytes]] = []
    if config.server_header and b"server" not in configured_names:
        default_headers.append((b"server", b"palfrey"))
    if config.date_header and b"date" not in configured_names:
        default_headers.append((b"date", _http_date_header()))
    default_headers.extend(configured_headers)
    return default_headers


def _merge_websocket_accept_headers(
    config: PalfreyConfig,
    message_headers: Any,
) -> list[tuple[bytes, bytes]]:
    return _default_websocket_headers(config) + _wsproto_extra_headers(message_headers)


def build_handshake_response(
    headers: list[tuple[str, str]],
    *,
    subprotocol: str | None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> bytes:
    """Create HTTP 101 response bytes for websocket upgrade."""

    client_key = _header_value(headers, "sec-websocket-key")
    if not client_key:
        raise ValueError("Missing Sec-WebSocket-Key")

    return _build_handshake_response_for_key(
        client_key,
        subprotocol=subprotocol,
        extra_headers=extra_headers,
    )


def _validate_handshake(headers: list[tuple[str, str]]) -> None:
    version = _header_value(headers, "sec-websocket-version")
    if version != "13":
        raise ValueError("Unsupported websocket version")

    key = _header_value(headers, "sec-websocket-key")
    if not key:
        raise ValueError("Missing Sec-WebSocket-Key")

    try:
        decoded = base64.b64decode(key.encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid Sec-WebSocket-Key") from exc

    if len(decoded) != 16:
        raise ValueError("Invalid Sec-WebSocket-Key length")


def _validate_handshake_from_map(headers_map: dict[str, str]) -> str:
    """Validate websocket handshake headers and return client key."""

    version = headers_map.get("sec-websocket-version")
    if version != "13":
        raise ValueError("Unsupported websocket version")

    key = headers_map.get("sec-websocket-key")
    if not key:
        raise ValueError("Missing Sec-WebSocket-Key")

    try:
        decoded = base64.b64decode(key.encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid Sec-WebSocket-Key") from exc

    if len(decoded) != 16:
        raise ValueError("Invalid Sec-WebSocket-Key length")

    return key


def _encode_frame(opcode: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    if length <= 125:
        return bytes((0x80 | opcode, length)) + payload
    if length <= 65_535:
        return bytes((0x80 | opcode, 126)) + struct.pack("!H", length) + payload
    return bytes((0x80 | opcode, 127)) + struct.pack("!Q", length) + payload


def _write_frame(writer: asyncio.StreamWriter, opcode: int, payload: bytes = b"") -> None:
    """Write one server frame to stream writer with minimal copying."""

    length = len(payload)
    if length <= 125:
        header = bytes((0x80 | opcode, length))
    elif length <= 65_535:
        header = bytes((0x80 | opcode, 126)) + struct.pack("!H", length)
    else:
        header = bytes((0x80 | opcode, 127)) + struct.pack("!Q", length)

    writelines = getattr(writer, "writelines", None)
    if payload and callable(writelines):
        writelines((header, payload))
        return

    writer.write(header + payload)


async def _read_frame(reader: asyncio.StreamReader, max_size: int) -> WebSocketFrame:
    first_two = await reader.readexactly(2)
    first, second = first_two[0], first_two[1]
    fin = (first & 0x80) != 0
    opcode = first & 0x0F

    masked = (second & 0x80) != 0
    length = second & 0x7F

    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]

    if length > max_size:
        raise ValueError("WebSocket frame exceeds ws_max_size")

    if not masked:
        raise ValueError("Client websocket frames must be masked")

    masking_key = await reader.readexactly(4)
    masked_payload = await reader.readexactly(length)
    payload = unmask_websocket_payload(masked_payload, masking_key)

    return WebSocketFrame(fin=fin, opcode=opcode, payload=payload)


def _try_parse_frame_from_buffer(
    buffer: bytearray,
    *,
    max_size: int,
) -> tuple[WebSocketFrame, int] | None:
    """Parse one websocket frame from a mutable buffer if enough bytes exist."""

    if len(buffer) < 2:
        return None

    view = memoryview(buffer)
    first = view[0]
    second = view[1]
    fin = (first & 0x80) != 0
    opcode = first & 0x0F

    masked = (second & 0x80) != 0
    payload_length = second & 0x7F
    offset = 2

    if payload_length == 126:
        if len(buffer) < offset + 2:
            return None
        payload_length = struct.unpack_from("!H", view, offset)[0]
        offset += 2
    elif payload_length == 127:
        if len(buffer) < offset + 8:
            return None
        payload_length = struct.unpack_from("!Q", view, offset)[0]
        offset += 8

    if payload_length > max_size:
        raise ValueError("WebSocket frame exceeds ws_max_size")

    if not masked:
        raise ValueError("Client websocket frames must be masked")

    total_size = offset + 4 + payload_length
    if len(buffer) < total_size:
        return None

    masking_key = bytes(view[offset : offset + 4])
    masked_payload = view[offset + 4 : total_size]
    payload = unmask_websocket_payload(masked_payload, masking_key)
    frame = WebSocketFrame(fin=fin, opcode=opcode, payload=payload)
    return frame, total_size


def _bad_websocket_request_payload() -> bytes:
    return (
        b"HTTP/1.1 400 Bad Request\r\n"
        b"content-length: 19\r\n"
        b"connection: close\r\n\r\n"
        b"Bad WebSocket Request"
    )


def _http_reason_phrase(status_code: int) -> str:
    mapping = {
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
    }
    return mapping.get(status_code, "WebSocket Response")


async def _write_bad_websocket_request(writer: asyncio.StreamWriter) -> None:
    writer.write(_bad_websocket_request_payload())
    await writer.drain()


async def _flush_websockets_output(connection: Any, writer: asyncio.StreamWriter) -> None:
    """Flush pending bytes generated by websockets protocol engines."""

    output = connection.data_to_send()
    if isinstance(output, (bytes, bytearray)):
        payload = bytes(output)
    else:
        payload = b"".join(cast("list[bytes]", output))
    if payload:
        writer.write(payload)
        await writer.drain()


async def _handle_websocket_core(
    app: ASGIApplication,
    config: PalfreyConfig,
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
    target: str,
    client: ClientAddress,
    server: ServerAddress,
    is_tls: bool,
) -> None:
    """Run the clean-room Palfrey WebSocket backend."""

    headers_map = _header_map(headers)
    try:
        client_key = _validate_handshake_from_map(headers_map)
    except ValueError:
        await _write_bad_websocket_request(writer)
        return

    scope = build_websocket_scope(
        target=target,
        headers=headers,
        client=client,
        server=server,
        root_path=config.root_path,
        is_tls=is_tls,
        protocol_header=headers_map.get("sec-websocket-protocol"),
    )

    accepted = False
    closed = False
    close_disconnect_code = 1000
    accept_subprotocol: str | None = None
    http_response_started = False
    http_response_status = 500
    http_response_headers: list[tuple[bytes, bytes]] = []
    http_response_body_chunks: list[bytes] = []
    fragmented_opcode: int | None = None
    fragmented_chunks: list[bytes] = []
    read_buffer = bytearray()
    transport = getattr(writer, "transport", None) or getattr(writer, "_transport", None)
    high_watermark_bytes = 262_144

    async def _flush_if_needed(*, force: bool = False) -> None:
        if force:
            await writer.drain()
            return
        if transport is None:
            return
        get_size = getattr(transport, "get_write_buffer_size", None)
        if callable(get_size) and int(get_size()) >= high_watermark_bytes:
            await writer.drain()

    async def receive() -> Message:
        nonlocal closed, close_disconnect_code, fragmented_opcode

        while True:
            if closed:
                return {"type": "websocket.disconnect", "code": close_disconnect_code}

            while True:
                parsed = _try_parse_frame_from_buffer(read_buffer, max_size=config.ws_max_size)
                if parsed is not None:
                    frame, consumed = parsed
                    del read_buffer[:consumed]
                    break

                chunk = await reader.read(65_536)
                if not chunk:
                    closed = True
                    return {"type": "websocket.disconnect", "code": 1005 if accepted else 1006}
                read_buffer.extend(chunk)

            if frame.opcode == 0x8:
                closed = True
                code = 1000
                if len(frame.payload) >= 2:
                    code = struct.unpack("!H", frame.payload[:2])[0]
                return {"type": "websocket.disconnect", "code": code}

            if frame.opcode == 0x9:
                _write_frame(writer, 0xA, frame.payload)
                await _flush_if_needed()
                continue

            if frame.opcode == 0xA:
                continue

            if frame.opcode == 0x0:
                if fragmented_opcode is None:
                    return {"type": "websocket.disconnect", "code": 1002}
                fragmented_chunks.append(frame.payload)
                if not frame.fin:
                    continue
                payload = b"".join(fragmented_chunks)
                opcode = fragmented_opcode
                fragmented_opcode = None
                fragmented_chunks.clear()
                if opcode == 0x1:
                    try:
                        return {"type": "websocket.receive", "text": payload.decode("utf-8")}
                    except UnicodeDecodeError:
                        return {"type": "websocket.disconnect", "code": 1007}
                return {"type": "websocket.receive", "bytes": payload}

            if (frame.opcode & 0x08) == 0 and frame.opcode not in {0x1, 0x2}:
                return {"type": "websocket.disconnect", "code": 1002}

            if frame.opcode == 0x1:
                if not frame.fin:
                    fragmented_opcode = 0x1
                    fragmented_chunks.append(frame.payload)
                    continue
                try:
                    return {"type": "websocket.receive", "text": frame.payload.decode("utf-8")}
                except UnicodeDecodeError:
                    return {"type": "websocket.disconnect", "code": 1007}

            if frame.opcode == 0x2:
                if not frame.fin:
                    fragmented_opcode = 0x2
                    fragmented_chunks.append(frame.payload)
                    continue
                return {"type": "websocket.receive", "bytes": frame.payload}

            return {"type": "websocket.disconnect", "code": 1002}

    async def send(message: Message) -> None:
        nonlocal accepted, closed, close_disconnect_code, accept_subprotocol
        nonlocal http_response_started, http_response_status
        nonlocal http_response_headers, http_response_body_chunks

        message_type = message["type"]

        if message_type == "websocket.accept":
            if accepted:
                return

            accept_subprotocol = message.get("subprotocol")
            response = _build_handshake_response_for_key(
                client_key,
                subprotocol=accept_subprotocol,
                extra_headers=_merge_websocket_accept_headers(config, message.get("headers")),
            )
            writer.write(response)
            await _flush_if_needed(force=True)
            accepted = True
            return

        if message_type == "websocket.http.response.start":
            if accepted:
                raise RuntimeError("Cannot send websocket HTTP response after accept")
            if http_response_started:
                raise RuntimeError(
                    "Expected ASGI message 'websocket.http.response.body' "
                    "but got 'websocket.http.response.start'."
                )
            http_response_started = True
            http_response_status = int(message["status"])
            http_response_headers = _wsproto_extra_headers(message.get("headers"))
            http_response_body_chunks = []
            return

        if message_type == "websocket.http.response.body":
            if accepted:
                raise RuntimeError("Cannot send websocket HTTP response after accept")
            if not http_response_started:
                raise RuntimeError(
                    "websocket.http.response.body sent before websocket.http.response.start"
                )

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            http_response_body_chunks.append(body)

            if message.get("more_body", False):
                return

            payload = b"".join(http_response_body_chunks)
            header_lines = [
                f"HTTP/1.1 {http_response_status} {_http_reason_phrase(http_response_status)}".encode(
                    "latin-1"
                ),
                *[name + b": " + value for name, value in http_response_headers],
            ]
            if not any(name.lower() == b"content-length" for name, _ in http_response_headers):
                header_lines.append(b"content-length: " + str(len(payload)).encode("ascii"))
            if not any(name.lower() == b"connection" for name, _ in http_response_headers):
                header_lines.append(b"connection: close")

            writer.write(b"\r\n".join(header_lines) + b"\r\n\r\n" + payload)
            await _flush_if_needed(force=True)
            closed = True
            close_disconnect_code = 1006
            return

        if message_type == "websocket.send":
            if not accepted:
                raise RuntimeError("WebSocket send before accept")

            if "text" in message:
                _write_frame(writer, 0x1, message["text"].encode("utf-8"))
            else:
                _write_frame(writer, 0x2, message.get("bytes", b""))
            await _flush_if_needed()
            return

        if message_type == "websocket.close":
            if not accepted:
                writer.write(
                    b"HTTP/1.1 403 Forbidden\r\ncontent-length: 0\r\nconnection: close\r\n\r\n"
                )
                await _flush_if_needed(force=True)
                closed = True
                close_disconnect_code = 1006
                return

            code = int(message.get("code", 1000))
            reason = message.get("reason", "").encode("utf-8")
            payload = struct.pack("!H", code) + reason
            _write_frame(writer, 0x8, payload)
            await _flush_if_needed(force=True)
            closed = True
            close_disconnect_code = code
            return

        raise RuntimeError(f"Unsupported websocket ASGI message type: {message_type}")

    await app(scope, receive, send)

    if accepted and not closed:
        _write_frame(writer, 0x8, struct.pack("!H", 1000))
        await _flush_if_needed(force=True)


async def _handle_websocket_websockets_backend(
    app: ASGIApplication,
    config: PalfreyConfig,
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
    target: str,
    client: ClientAddress,
    server: ServerAddress,
    is_tls: bool,
) -> None:  # pragma: no cover
    """Handle websockets backend mode.

    This backend uses the ``websockets`` asyncio connection implementation
    (distinct from the clean-room frame engine and wsproto backend).
    """

    if find_spec("websockets") is None:
        raise RuntimeError("WebSocket mode 'websockets' requires the 'websockets' package.")

    transport = getattr(writer, "transport", None)
    if transport is None and hasattr(writer, "_transport"):
        transport = writer._transport
    if transport is None:
        await _handle_websocket_core(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=headers,
            target=target,
            client=client,
            server=server,
            is_tls=is_tls,
        )
        return

    websockets_server_module = cast(Any, importlib.import_module("websockets.server"))
    websockets_asyncio_server_module = cast(
        Any, importlib.import_module("websockets.asyncio.server")
    )
    websockets_exceptions_module = cast(Any, importlib.import_module("websockets.exceptions"))

    server_protocol_cls = websockets_server_module.ServerProtocol
    server_connection_cls = websockets_asyncio_server_module.ServerConnection
    connection_closed_exc = websockets_exceptions_module.ConnectionClosed
    per_message_deflate_factory = None
    if config.ws_per_message_deflate:
        try:
            permessage_module = cast(
                Any,
                importlib.import_module("websockets.extensions.permessage_deflate"),
            )
        except ImportError:
            per_message_deflate_factory = None
        else:
            per_message_deflate_factory = permessage_module.ServerPerMessageDeflateFactory

    class _FakeWebSocketServer:
        def register(self, ws: Any) -> None:
            return None

        def unregister(self, ws: Any) -> None:
            return None

        def is_serving(self) -> bool:
            return True

        def start_connection_handler(self, _connection: Any) -> None:
            # websockets >=16 calls this hook from connection_made().
            return None

    protocol_kwargs: dict[str, Any] = {
        "max_size": config.ws_max_size,
    }
    if per_message_deflate_factory is not None:
        protocol_kwargs["extensions"] = [per_message_deflate_factory()]

    protocol = server_protocol_cls(**protocol_kwargs)
    connection = server_connection_cls(
        protocol,
        _FakeWebSocketServer(),
        ping_interval=config.ws_ping_interval,
        ping_timeout=config.ws_ping_timeout,
        max_queue=config.ws_max_queue,
    )
    connection.connection_made(transport)
    connection.data_received(_build_wsproto_upgrade_request(target, headers))

    scope = build_websocket_scope(
        target=target,
        headers=headers,
        client=client,
        server=server,
        root_path=config.root_path,
        is_tls=is_tls,
    )

    handshake_started = asyncio.Event()
    handshake_completed = asyncio.Event()
    app_done = asyncio.Event()
    closed = asyncio.Event()
    connect_sent = False
    accepted_subprotocol: str | None = None
    accepted_headers: list[tuple[bytes, bytes]] = []
    pending_http_response: list[tuple[int, list[tuple[bytes, bytes]], bytes] | None] = [None]
    handshake_accepted = False

    async def asgi_receive() -> Message:
        nonlocal connect_sent
        if not connect_sent:
            connect_sent = True
            return {"type": "websocket.connect"}

        await handshake_completed.wait()
        if closed.is_set():
            return {"type": "websocket.disconnect", "code": 1005 if handshake_accepted else 1006}

        try:
            payload = await connection.recv()
        except connection_closed_exc:
            closed.set()
            code = int(getattr(connection, "close_code", 1005) or 1005)
            reason = str(getattr(connection, "close_reason", "") or "")
            if reason:
                return {"type": "websocket.disconnect", "code": code, "reason": reason}
            return {"type": "websocket.disconnect", "code": code}

        if isinstance(payload, str):
            return {"type": "websocket.receive", "text": payload}
        return {"type": "websocket.receive", "bytes": bytes(payload)}

    async def asgi_send(message: Message) -> None:
        nonlocal accepted_subprotocol, accepted_headers, handshake_accepted

        message_type = message["type"]

        if not handshake_started.is_set():
            if message_type == "websocket.accept":
                accepted_subprotocol = message.get("subprotocol")
                accepted_headers = _merge_websocket_accept_headers(config, message.get("headers"))
                pending_http_response[0] = None
                handshake_accepted = True
                handshake_started.set()
                return

            if message_type == "websocket.close":
                pending_http_response[0] = (403, [], b"")
                handshake_started.set()
                closed.set()
                return

            if message_type == "websocket.http.response.start":
                pending_http_response[0] = (
                    int(message["status"]),
                    _wsproto_extra_headers(message.get("headers")),
                    b"",
                )
                handshake_started.set()
                return

            raise RuntimeError(
                "Expected ASGI message 'websocket.accept', 'websocket.close', "
                f"or 'websocket.http.response.start' but got '{message_type}'."
            )

        current_response = pending_http_response[0]
        if current_response is not None:
            if message_type != "websocket.http.response.body":
                raise RuntimeError(
                    "Expected ASGI message 'websocket.http.response.body' "
                    f"but got '{message_type}'."
                )

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            status, hdrs, payload = current_response
            pending_http_response[0] = (status, hdrs, payload + body)
            if not message.get("more_body", False):
                closed.set()
            return

        if closed.is_set():
            raise RuntimeError(
                f"Unexpected ASGI message '{message_type}', "
                "after sending 'websocket.close' or response already completed."
            )

        await handshake_completed.wait()
        if message_type == "websocket.send":
            if "text" in message:
                await connection.send(str(message["text"]))
            else:
                await connection.send(bytes(message.get("bytes", b"")))
            return

        if message_type == "websocket.close":
            code = int(message.get("code", 1000))
            reason = str(message.get("reason", ""))
            await connection.close(code, reason)
            closed.set()
            return

        raise RuntimeError(
            "Expected ASGI message 'websocket.send' or 'websocket.close', "
            f"but got '{message_type}'."
        )

    async def run_asgi() -> None:
        try:
            result = await app(scope, asgi_receive, asgi_send)
        except Exception:
            if not handshake_started.is_set():
                initial = (500, [(b"content-type", b"text/plain")], b"Internal Server Error")
                pending_http_response[0] = initial
                handshake_started.set()
            closed.set()
        else:
            if not handshake_started.is_set():
                pending_http_response[0] = (
                    500,
                    [(b"content-type", b"text/plain")],
                    b"ASGI callable returned without sending handshake.",
                )
                handshake_started.set()
            if result is not None:
                closed.set()
        finally:
            app_done.set()

    async def process_request(_conn: Any, _request: Any) -> Any:
        await asyncio.wait(
            [asyncio.create_task(handshake_started.wait()), asyncio.create_task(app_done.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        pending_initial = pending_http_response[0]
        if pending_initial is None:
            return None

        status, hdrs, payload = pending_initial
        response = _conn.respond(status, payload.decode("latin-1"))
        for name, value in hdrs:
            response.headers[name.decode("latin-1")] = value.decode("latin-1")
        return response

    async def process_response(_conn: Any, _request: Any, response: Any) -> Any:
        for name, value in accepted_headers:
            response.headers[name.decode("latin-1")] = value.decode("latin-1")
        if accepted_subprotocol:
            response.headers["Sec-WebSocket-Protocol"] = accepted_subprotocol
        return response

    app_task = asyncio.create_task(run_asgi())

    try:
        await connection.handshake(
            process_request=process_request,
            process_response=process_response,
            server_header=None,
        )
    except Exception:
        await _write_bad_websocket_request(writer)
        app_task.cancel()
        with contextlib.suppress(Exception):
            await app_task
        return

    handshake_completed.set()

    if pending_http_response[0] is not None:
        await app_done.wait()
        return

    async def pump_reader() -> None:
        while not closed.is_set():
            chunk = await reader.read(65_536)
            if not chunk:
                connection.connection_lost(None)
                break
            connection.data_received(chunk)

    reader_task = asyncio.create_task(pump_reader())
    done, pending = await asyncio.wait(
        {app_task, reader_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if app_task in done and not closed.is_set():
        with contextlib.suppress(Exception):
            await connection.close(1000, "")
        closed.set()

    for task in pending:
        task.cancel()
    for task in pending:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _handle_websocket_websockets_sansio_backend(
    app: ASGIApplication,
    config: PalfreyConfig,
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
    target: str,
    client: ClientAddress,
    server: ServerAddress,
    is_tls: bool,
) -> None:
    """Handle websockets-sansio backend mode.

    This backend mirrors Uvicorn's SansIO framing path by using
    ``websockets.server.ServerProtocol`` directly.
    """

    if find_spec("websockets") is None:
        raise RuntimeError("WebSocket mode 'websockets-sansio' requires the 'websockets' package.")

    websockets_server_module = cast(Any, importlib.import_module("websockets.server"))
    websockets_frames_module = cast(Any, importlib.import_module("websockets.frames"))
    websockets_exceptions_module = cast(Any, importlib.import_module("websockets.exceptions"))

    per_message_deflate_factory = None
    if config.ws_per_message_deflate:
        try:
            permessage_module = cast(
                Any,
                importlib.import_module("websockets.extensions.permessage_deflate"),
            )
        except ImportError:
            per_message_deflate_factory = None
        else:
            per_message_deflate_factory = permessage_module.ServerPerMessageDeflateFactory

    protocol_kwargs: dict[str, Any] = {
        "max_size": config.ws_max_size,
    }
    if per_message_deflate_factory is not None:
        try:
            protocol_kwargs["extensions"] = [
                per_message_deflate_factory(
                    server_max_window_bits=12,
                    client_max_window_bits=12,
                    compress_settings={"memLevel": 5},
                )
            ]
        except TypeError:
            protocol_kwargs["extensions"] = [per_message_deflate_factory()]

    server_protocol_cls = websockets_server_module.ServerProtocol
    frame_cls = websockets_frames_module.Frame
    opcode_cls = websockets_frames_module.Opcode
    invalid_state_exc = websockets_exceptions_module.InvalidState
    parser_exc_cls = tuple(
        item
        for item in (
            getattr(websockets_exceptions_module, "ProtocolError", None),
            getattr(websockets_exceptions_module, "PayloadTooBig", None),
            getattr(websockets_exceptions_module, "InvalidState", None),
        )
        if isinstance(item, type)
    )

    conn = server_protocol_cls(**protocol_kwargs)
    try:
        conn.receive_data(_build_wsproto_upgrade_request(target, headers))
    except Exception:
        await _write_bad_websocket_request(writer)
        return

    request_event = None
    for event in conn.events_received():
        if event.__class__.__name__ == "Request":
            request_event = event
            break
    if request_event is None:
        await _write_bad_websocket_request(writer)
        return

    upgrade_response = conn.accept(request_event)
    if int(getattr(upgrade_response, "status_code", 500)) != 101:
        conn.send_response(upgrade_response)
        await _flush_websockets_output(conn, writer)
        return

    scope = build_websocket_scope(
        target=str(getattr(request_event, "path", target)),
        headers=headers,
        client=client,
        server=server,
        root_path=config.root_path,
        is_tls=is_tls,
    )

    queue: asyncio.Queue[Message] = asyncio.Queue()
    queue.put_nowait({"type": "websocket.connect"})

    handshake_complete = False
    close_sent = False
    initial_response: tuple[int, list[tuple[str, str]], bytes] | None = None
    fragmented_type: str | None = None
    fragmented_payload = bytearray()

    async def send_500_response() -> None:
        nonlocal close_sent, handshake_complete
        if initial_response is not None or handshake_complete:
            return
        response = conn.reject(500, "Internal Server Error")
        conn.send_response(response)
        await _flush_websockets_output(conn, writer)
        close_sent = True
        handshake_complete = True

    async def process_frame(frame: Any) -> None:
        nonlocal close_sent, fragmented_type

        if frame.opcode == opcode_cls.PING:
            await _flush_websockets_output(conn, writer)
            return
        if frame.opcode == opcode_cls.PONG:
            return
        if frame.opcode == opcode_cls.CLOSE:
            close_rcvd = getattr(conn, "close_rcvd", None)
            code = int(getattr(close_rcvd, "code", 1000) or 1000)
            reason = str(getattr(close_rcvd, "reason", "") or "")
            message: Message = {"type": "websocket.disconnect", "code": code}
            if reason:
                message["reason"] = reason
            queue.put_nowait(message)
            await _flush_websockets_output(conn, writer)
            close_sent = True
            return

        if frame.opcode == opcode_cls.CONT:
            if fragmented_type is None:
                queue.put_nowait({"type": "websocket.disconnect", "code": 1002})
                conn.send_close(1002, "unexpected continuation frame")
                await _flush_websockets_output(conn, writer)
                close_sent = True
                return
            fragmented_payload.extend(bytes(frame.data))
            if not frame.fin:
                return
            payload = bytes(fragmented_payload)
            fragmented_payload.clear()
            current_type = fragmented_type
            fragmented_type = None
            if current_type == "text":
                try:
                    queue.put_nowait({"type": "websocket.receive", "text": payload.decode("utf-8")})
                except UnicodeDecodeError:
                    queue.put_nowait({"type": "websocket.disconnect", "code": 1007})
                    conn.send_close(1007, "invalid UTF-8 payload")
                    await _flush_websockets_output(conn, writer)
                    close_sent = True
            else:
                queue.put_nowait({"type": "websocket.receive", "bytes": payload})
            return

        if frame.opcode == opcode_cls.TEXT:
            payload = bytes(frame.data)
            if frame.fin:
                try:
                    queue.put_nowait({"type": "websocket.receive", "text": payload.decode("utf-8")})
                except UnicodeDecodeError:
                    queue.put_nowait({"type": "websocket.disconnect", "code": 1007})
                    conn.send_close(1007, "invalid UTF-8 payload")
                    await _flush_websockets_output(conn, writer)
                    close_sent = True
                return
            fragmented_type = "text"
            fragmented_payload[:] = payload
            return

        if frame.opcode == opcode_cls.BINARY:
            payload = bytes(frame.data)
            if frame.fin:
                queue.put_nowait({"type": "websocket.receive", "bytes": payload})
                return
            fragmented_type = "bytes"
            fragmented_payload[:] = payload
            return

        queue.put_nowait({"type": "websocket.disconnect", "code": 1002})
        conn.send_close(1002, "unsupported frame opcode")
        await _flush_websockets_output(conn, writer)
        close_sent = True

    async def pump_reader() -> None:
        nonlocal close_sent

        while not close_sent:
            packet = await reader.read(65_536)
            if not packet:
                queue.put_nowait(
                    {"type": "websocket.disconnect", "code": 1005 if handshake_complete else 1006}
                )
                return

            if parser_exc_cls:
                try:
                    conn.receive_data(packet)
                except parser_exc_cls:
                    queue.put_nowait({"type": "websocket.disconnect", "code": 1002})
                    close_sent = True
                    return
            else:
                conn.receive_data(packet)

            parser_exc = getattr(conn, "parser_exc", None)
            if parser_exc is not None:
                close_sent_obj = getattr(conn, "close_sent", None)
                code = int(getattr(close_sent_obj, "code", 1002) or 1002)
                reason = str(getattr(close_sent_obj, "reason", "") or "")
                message: Message = {"type": "websocket.disconnect", "code": code}
                if reason:
                    message["reason"] = reason
                queue.put_nowait(message)
                await _flush_websockets_output(conn, writer)
                close_sent = True
                return

            for event in conn.events_received():
                if isinstance(event, frame_cls):
                    await process_frame(event)
                    if close_sent:
                        return

    async def receive() -> Message:
        return await queue.get()

    async def send(message: Message) -> None:
        nonlocal handshake_complete, close_sent, initial_response

        message_type = message["type"]

        if not handshake_complete and initial_response is None:
            if message_type == "websocket.accept":
                accept_headers = [
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in _merge_websocket_accept_headers(
                        config, message.get("headers")
                    )
                ]
                subprotocol = message.get("subprotocol")
                if subprotocol:
                    accept_headers.append(("Sec-WebSocket-Protocol", str(subprotocol)))
                upgrade_response.headers.update(accept_headers)
                conn.send_response(upgrade_response)
                await _flush_websockets_output(conn, writer)
                handshake_complete = True
                return

            if message_type == "websocket.close":
                queue.put_nowait({"type": "websocket.disconnect", "code": 1006})
                reject_response = conn.reject(403, "")
                conn.send_response(reject_response)
                await _flush_websockets_output(conn, writer)
                handshake_complete = True
                close_sent = True
                return

            if message_type == "websocket.http.response.start":
                status = int(message["status"])
                if not (100 <= status < 600):
                    raise RuntimeError(f"Invalid HTTP status code '{status}' in response.")
                initial_response = (
                    status,
                    [
                        (name.decode("latin-1"), value.decode("latin-1"))
                        for name, value in _wsproto_extra_headers(message.get("headers"))
                    ],
                    b"",
                )
                return

            raise RuntimeError(
                "Expected ASGI message 'websocket.accept', 'websocket.close' "
                f"or 'websocket.http.response.start' but got '{message_type}'."
            )

        if not close_sent and initial_response is None:
            try:
                if message_type == "websocket.send":
                    if "text" in message:
                        conn.send_text(str(message["text"]).encode("utf-8"))
                    else:
                        conn.send_binary(bytes(message.get("bytes", b"")))
                    await _flush_websockets_output(conn, writer)
                    return

                if message_type == "websocket.close":
                    code = int(message.get("code", 1000))
                    reason = str(message.get("reason", "") or "")
                    disconnect_message: Message = {"type": "websocket.disconnect", "code": code}
                    if reason:
                        disconnect_message["reason"] = reason
                    queue.put_nowait(disconnect_message)
                    conn.send_close(code, reason)
                    await _flush_websockets_output(conn, writer)
                    close_sent = True
                    return

                raise RuntimeError(
                    "Expected ASGI message 'websocket.send' or 'websocket.close', "
                    f"but got '{message_type}'."
                )
            except invalid_state_exc:
                queue.put_nowait({"type": "websocket.disconnect", "code": 1006})
                close_sent = True
                return

        if initial_response is not None:
            if message_type != "websocket.http.response.body":
                raise RuntimeError(
                    "Expected ASGI message 'websocket.http.response.body' "
                    f"but got '{message_type}'."
                )

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            status, response_headers, payload = initial_response
            payload += body
            initial_response = (status, response_headers, payload)
            if message.get("more_body", False):
                return

            reject_response = conn.reject(status, payload.decode("utf-8"))
            reject_response.headers.update(response_headers)
            queue.put_nowait({"type": "websocket.disconnect", "code": 1006})
            conn.send_response(reject_response)
            await _flush_websockets_output(conn, writer)
            close_sent = True
            return

        raise RuntimeError(
            f"Unexpected ASGI message '{message_type}', after sending 'websocket.close'."
        )

    async def run_asgi() -> None:
        try:
            result = await app(scope, receive, send)
        except Exception:
            await send_500_response()
        else:
            if not handshake_complete:
                await send_500_response()
            elif result is not None:
                close_sent_message = {"type": "websocket.disconnect", "code": 1006}
                queue.put_nowait(close_sent_message)

    app_task = asyncio.create_task(run_asgi())
    reader_task = asyncio.create_task(pump_reader())
    done, pending = await asyncio.wait({app_task, reader_task}, return_when=asyncio.FIRST_COMPLETED)

    if app_task in done and not close_sent and handshake_complete:
        conn.send_close(1000, "")
        await _flush_websockets_output(conn, writer)

    for task in pending:
        task.cancel()
    for task in pending:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def _build_wsproto_upgrade_request(target: str, headers: list[tuple[str, str]]) -> bytes:
    """Build synthetic HTTP upgrade bytes for wsproto state initialization."""

    request_headers = [f"GET {target} HTTP/1.1"]
    request_headers.extend(f"{name}: {value}" for name, value in headers)
    request_headers.extend(["", ""])
    return "\r\n".join(request_headers).encode("latin-1")


def _wsproto_extra_headers(
    message_headers: Any,
) -> list[tuple[bytes, bytes]]:
    """Normalize ASGI websocket.accept headers to wsproto header tuples."""

    extra_headers: list[tuple[bytes, bytes]] = []
    for item in message_headers or []:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        name_raw, value_raw = item
        if isinstance(name_raw, bytes):
            name = name_raw
        else:
            name = str(name_raw).encode("latin-1")
        if isinstance(value_raw, bytes):
            value = value_raw
        else:
            value = str(value_raw).encode("latin-1")
        extra_headers.append((name, value))
    return extra_headers


async def _handle_websocket_wsproto_backend(
    app: ASGIApplication,
    config: PalfreyConfig,
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
    target: str,
    client: ClientAddress,
    server: ServerAddress,
    is_tls: bool,
) -> None:
    """Handle wsproto backend mode with wsproto-driven frame processing."""

    if find_spec("wsproto") is None:
        raise RuntimeError("WebSocket mode 'wsproto' requires the 'wsproto' package.")

    try:
        _validate_handshake(headers)
    except ValueError:
        await _write_bad_websocket_request(writer)
        return

    wsproto_module = cast(Any, importlib.import_module("wsproto"))
    events_module = cast(Any, importlib.import_module("wsproto.events"))
    connection_module = cast(Any, importlib.import_module("wsproto.connection"))
    extensions_module = cast(Any, importlib.import_module("wsproto.extensions"))
    utilities_module = cast(Any, importlib.import_module("wsproto.utilities"))

    ws_connection_cls = wsproto_module.WSConnection
    connection_type = wsproto_module.ConnectionType
    local_protocol_error = utilities_module.LocalProtocolError
    remote_protocol_error = utilities_module.RemoteProtocolError
    connection_state = connection_module.ConnectionState

    event_request_cls = events_module.Request
    event_ping_cls = events_module.Ping
    event_pong_cls = events_module.Pong
    event_message_cls = events_module.Message
    event_text_cls = events_module.TextMessage
    event_bytes_cls = events_module.BytesMessage
    event_close_cls = events_module.CloseConnection
    accept_connection_cls = events_module.AcceptConnection
    close_connection_cls = events_module.CloseConnection

    per_message_deflate_cls = (
        extensions_module.PerMessageDeflate
        if hasattr(extensions_module, "PerMessageDeflate")
        else None
    )

    scope = build_websocket_scope(
        target=target,
        headers=headers,
        client=client,
        server=server,
        root_path=config.root_path,
        is_tls=is_tls,
    )

    conn = ws_connection_cls(connection_type=connection_type.SERVER)
    request_received = False
    try:
        conn.receive_data(_build_wsproto_upgrade_request(target, headers))
        for event in conn.events():
            if isinstance(event, event_request_cls):
                request_received = True
                break
    except (local_protocol_error, remote_protocol_error):
        await _write_bad_websocket_request(writer)
        return
    if not request_received:
        await _write_bad_websocket_request(writer)
        return

    accepted = False
    closed = False
    close_disconnect_code = 1000
    receive_lock = asyncio.Lock()
    text_chunks: list[str] = []
    bytes_chunks: list[bytes] = []
    http_response_started = False
    http_response_status = 500
    http_response_headers: list[tuple[bytes, bytes]] = []
    http_response_body_chunks: list[bytes] = []

    async def receive() -> Message:
        nonlocal closed, close_disconnect_code

        async with receive_lock:
            while True:
                if closed:
                    return {"type": "websocket.disconnect", "code": close_disconnect_code}

                packet = await reader.read(65_536)
                if not packet:
                    closed = True
                    close_disconnect_code = 1005 if accepted else 1006
                    return {"type": "websocket.disconnect", "code": close_disconnect_code}

                try:
                    conn.receive_data(packet)
                except (local_protocol_error, remote_protocol_error):
                    closed = True
                    close_disconnect_code = 1002
                    return {"type": "websocket.disconnect", "code": close_disconnect_code}

                for event in conn.events():
                    if isinstance(event, event_ping_cls):
                        writer.write(conn.send(event.response()))
                        await writer.drain()
                        continue

                    if isinstance(event, event_pong_cls):
                        continue

                    if isinstance(event, event_text_cls):
                        text_chunks.append(str(event.data))
                        if not event.message_finished:
                            continue
                        payload = "".join(text_chunks)
                        text_chunks.clear()
                        return {"type": "websocket.receive", "text": payload}

                    if isinstance(event, event_bytes_cls):
                        chunk = bytes(event.data)
                        bytes_chunks.append(chunk)
                        total_size = sum(len(item) for item in bytes_chunks)
                        if total_size > config.ws_max_size:
                            closed = True
                            close_disconnect_code = 1009
                            return {"type": "websocket.disconnect", "code": close_disconnect_code}
                        if not event.message_finished:
                            continue
                        payload = b"".join(bytes_chunks)
                        bytes_chunks.clear()
                        return {"type": "websocket.receive", "bytes": payload}

                    if isinstance(event, event_close_cls):
                        closed = True
                        if getattr(conn, "state", None) == connection_state.REMOTE_CLOSING:
                            writer.write(conn.send(event.response()))
                            await writer.drain()
                        code = int(getattr(event, "code", 1000))
                        close_disconnect_code = code
                        reason = str(getattr(event, "reason", ""))
                        if reason:
                            return {"type": "websocket.disconnect", "code": code, "reason": reason}
                        return {"type": "websocket.disconnect", "code": code}

                # Ignore request/other handshake events after initialization.

    async def send(message: Message) -> None:
        nonlocal accepted, closed, close_disconnect_code
        nonlocal http_response_started, http_response_status
        nonlocal http_response_headers, http_response_body_chunks

        message_type = message["type"]

        if message_type == "websocket.accept":
            if accepted:
                return

            subprotocol = message.get("subprotocol")
            extensions = []
            if config.ws_per_message_deflate and per_message_deflate_cls is not None:
                extensions.append(per_message_deflate_cls())

            event = accept_connection_cls(
                subprotocol=subprotocol,
                extensions=extensions,
                extra_headers=_merge_websocket_accept_headers(config, message.get("headers")),
            )
            writer.write(conn.send(event))
            await writer.drain()
            accepted = True
            return

        if message_type == "websocket.send":
            if not accepted:
                raise RuntimeError("WebSocket send before accept")

            payload: str | bytes
            if "text" in message:
                payload = str(message["text"])
            else:
                payload = bytes(message.get("bytes", b""))

            writer.write(conn.send(event_message_cls(data=payload)))
            await writer.drain()
            return

        if message_type == "websocket.http.response.start":
            if accepted:
                raise RuntimeError("Cannot send websocket HTTP response after accept")
            if http_response_started:
                raise RuntimeError(
                    "Expected ASGI message 'websocket.http.response.body' "
                    "but got 'websocket.http.response.start'."
                )
            http_response_started = True
            status = int(message["status"])
            if not (100 <= status < 600):
                raise RuntimeError(f"Invalid HTTP status code '{status}' in response.")
            http_response_status = status
            http_response_headers = _wsproto_extra_headers(message.get("headers"))
            http_response_body_chunks = []
            return

        if message_type == "websocket.http.response.body":
            if accepted:
                raise RuntimeError("Cannot send websocket HTTP response after accept")
            if not http_response_started:
                raise RuntimeError(
                    "websocket.http.response.body sent before websocket.http.response.start"
                )

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            http_response_body_chunks.append(body)

            if message.get("more_body", False):
                return

            payload = b"".join(http_response_body_chunks)
            header_lines = [
                f"HTTP/1.1 {http_response_status} {_http_reason_phrase(http_response_status)}".encode(
                    "latin-1"
                ),
                *[name + b": " + value for name, value in http_response_headers],
            ]
            if not any(name.lower() == b"content-length" for name, _ in http_response_headers):
                header_lines.append(b"content-length: " + str(len(payload)).encode("ascii"))
            if not any(name.lower() == b"connection" for name, _ in http_response_headers):
                header_lines.append(b"connection: close")

            writer.write(b"\r\n".join(header_lines) + b"\r\n\r\n" + payload)
            await writer.drain()
            closed = True
            close_disconnect_code = 1006
            return

        if message_type == "websocket.close":
            code = int(message.get("code", 1000))
            reason = str(message.get("reason", ""))
            if not accepted:
                writer.write(
                    b"HTTP/1.1 403 Forbidden\r\ncontent-length: 0\r\nconnection: close\r\n\r\n"
                )
                await writer.drain()
                closed = True
                close_disconnect_code = 1006
                return

            writer.write(conn.send(close_connection_cls(code=code, reason=reason)))
            await writer.drain()
            closed = True
            close_disconnect_code = code
            return

        raise RuntimeError(f"Unsupported websocket ASGI message type: {message_type}")

    await app(scope, receive, send)

    if accepted and not closed:
        writer.write(conn.send(close_connection_cls(code=1000, reason="")))
        await writer.drain()


async def handle_websocket(
    app: ASGIApplication,
    config: PalfreyConfig,
    *,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
    target: str,
    client: ClientAddress,
    server: ServerAddress,
    is_tls: bool,
) -> None:
    """Run the ASGI websocket flow for a single client connection.

    Backend dispatch matches Uvicorn mode semantics:
    - ``websockets`` -> websockets backend path
    - ``websockets-sansio`` -> sansio backend path
    - ``wsproto`` -> wsproto backend path
    - ``none`` -> clean-room fallback path (used only for direct invocation)
    """

    selected_ws = config.effective_ws
    if selected_ws == "wsproto":
        await _handle_websocket_wsproto_backend(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=headers,
            target=target,
            client=client,
            server=server,
            is_tls=is_tls,
        )
        return

    if selected_ws == "websockets-sansio":
        await _handle_websocket_websockets_sansio_backend(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=headers,
            target=target,
            client=client,
            server=server,
            is_tls=is_tls,
        )
        return

    if selected_ws == "none":
        await _handle_websocket_core(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=headers,
            target=target,
            client=client,
            server=server,
            is_tls=is_tls,
        )
        return

    await _handle_websocket_websockets_backend(
        app,
        config,
        reader=reader,
        writer=writer,
        headers=headers,
        target=target,
        client=client,
        server=server,
        is_tls=is_tls,
    )
