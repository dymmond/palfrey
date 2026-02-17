"""WebSocket protocol support for Palfrey."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
from dataclasses import dataclass

from palfrey.config import PalfreyConfig
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


def build_websocket_scope(
    *,
    target: str,
    headers: list[tuple[str, str]],
    client: ClientAddress,
    server: ServerAddress,
    root_path: str,
    is_tls: bool,
) -> Scope:
    """Build an ASGI websocket scope."""

    path, _, query = target.partition("?")

    protocol_header = _header_value(headers, "sec-websocket-protocol")
    subprotocols = []
    if protocol_header:
        subprotocols = [item.strip() for item in protocol_header.split(",") if item.strip()]

    return {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "scheme": "wss" if is_tls else "ws",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": query.encode("latin-1"),
        "root_path": root_path,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers
        ],
        "client": client,
        "server": server,
        "subprotocols": subprotocols,
        "state": {},
    }


def _accept_value(client_key: str) -> str:
    token = (client_key + _WS_GUID).encode("latin-1")
    digest = hashlib.sha1(token, usedforsecurity=False).digest()
    return base64.b64encode(digest).decode("ascii")


def build_handshake_response(
    headers: list[tuple[str, str]],
    *,
    subprotocol: str | None,
) -> bytes:
    """Create HTTP 101 response bytes for websocket upgrade."""

    client_key = _header_value(headers, "sec-websocket-key")
    if not client_key:
        raise ValueError("Missing Sec-WebSocket-Key")

    response_headers = [
        b"HTTP/1.1 101 Switching Protocols",
        b"upgrade: websocket",
        b"connection: Upgrade",
        b"sec-websocket-accept: " + _accept_value(client_key).encode("ascii"),
    ]

    if subprotocol:
        response_headers.append(b"sec-websocket-protocol: " + subprotocol.encode("latin-1"))

    return b"\r\n".join(response_headers) + b"\r\n\r\n"


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


def _encode_frame(opcode: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    header = bytearray()
    header.append(0x80 | opcode)

    if length <= 125:
        header.append(length)
    elif length <= 65_535:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))

    return bytes(header) + payload


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

    masking_key = b""
    if masked:
        masking_key = await reader.readexactly(4)

    payload = await reader.readexactly(length)

    if masked:
        payload = bytes(byte ^ masking_key[index % 4] for index, byte in enumerate(payload))

    return WebSocketFrame(fin=fin, opcode=opcode, payload=payload)


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
    """Run the ASGI websocket flow for a single client connection."""

    try:
        _validate_handshake(headers)
    except ValueError:
        writer.write(
            b"HTTP/1.1 400 Bad Request\r\n"
            b"content-length: 19\r\n"
            b"connection: close\r\n\r\n"
            b"Bad WebSocket Request"
        )
        await writer.drain()
        return

    scope = build_websocket_scope(
        target=target,
        headers=headers,
        client=client,
        server=server,
        root_path=config.root_path,
        is_tls=is_tls,
    )

    accepted = False
    closed = False
    accept_subprotocol: str | None = None
    receive_lock = asyncio.Lock()
    fragmented_opcode: int | None = None
    fragmented_chunks: list[bytes] = []

    async def receive() -> Message:
        nonlocal closed, fragmented_opcode

        async with receive_lock:
            if closed:
                return {"type": "websocket.disconnect", "code": 1000}

            frame = await _read_frame(reader, config.ws_max_size)

            if frame.opcode == 0x8:
                closed = True
                code = 1000
                if len(frame.payload) >= 2:
                    code = struct.unpack("!H", frame.payload[:2])[0]
                return {"type": "websocket.disconnect", "code": code}

            if frame.opcode == 0x9:
                writer.write(_encode_frame(0xA, frame.payload))
                await writer.drain()
                return await receive()

            if frame.opcode == 0xA:
                return await receive()

            if frame.opcode == 0x0:
                if fragmented_opcode is None:
                    return {"type": "websocket.disconnect", "code": 1002}
                fragmented_chunks.append(frame.payload)
                if not frame.fin:
                    return await receive()
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
                    return await receive()
                try:
                    return {"type": "websocket.receive", "text": frame.payload.decode("utf-8")}
                except UnicodeDecodeError:
                    return {"type": "websocket.disconnect", "code": 1007}

            if frame.opcode == 0x2:
                if not frame.fin:
                    fragmented_opcode = 0x2
                    fragmented_chunks.append(frame.payload)
                    return await receive()
                return {"type": "websocket.receive", "bytes": frame.payload}

            return {"type": "websocket.disconnect", "code": 1002}

    async def send(message: Message) -> None:
        nonlocal accepted, closed, accept_subprotocol

        message_type = message["type"]

        if message_type == "websocket.accept":
            if accepted:
                return

            accept_subprotocol = message.get("subprotocol")
            response = build_handshake_response(headers, subprotocol=accept_subprotocol)
            writer.write(response)
            await writer.drain()
            accepted = True
            return

        if message_type == "websocket.send":
            if not accepted:
                raise RuntimeError("WebSocket send before accept")

            if "text" in message:
                writer.write(_encode_frame(0x1, message["text"].encode("utf-8")))
            else:
                writer.write(_encode_frame(0x2, message.get("bytes", b"")))
            await writer.drain()
            return

        if message_type == "websocket.close":
            code = int(message.get("code", 1000))
            reason = message.get("reason", "").encode("utf-8")
            payload = struct.pack("!H", code) + reason
            writer.write(_encode_frame(0x8, payload))
            await writer.drain()
            closed = True
            return

        raise RuntimeError(f"Unsupported websocket ASGI message type: {message_type}")

    await app(scope, receive, send)

    if accepted and not closed:
        writer.write(_encode_frame(0x8, struct.pack("!H", 1000)))
        await writer.drain()
