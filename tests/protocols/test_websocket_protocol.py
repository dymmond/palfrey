"""WebSocket protocol helper tests."""

from __future__ import annotations

import asyncio
import base64
import os
import struct

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.websocket import (
    _read_frame,
    build_handshake_response,
    build_websocket_scope,
    handle_websocket,
)
from tests.helpers import make_stream_reader


def _masked_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    mask = os.urandom(4)
    first = (0x80 if fin else 0x00) | opcode
    header = bytearray([first])
    length = len(payload)
    if length <= 125:
        header.append(0x80 | length)
    elif length <= 65_535:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))

    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + mask + masked


def _handshake_headers(*, protocol: str | None = None) -> list[tuple[str, str]]:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    headers = [
        ("upgrade", "websocket"),
        ("connection", "Upgrade"),
        ("sec-websocket-key", key),
        ("sec-websocket-version", "13"),
    ]
    if protocol:
        headers.append(("sec-websocket-protocol", protocol))
    return headers


def _decode_server_frame(payload: bytes) -> tuple[int, bytes]:
    first = payload[0]
    second = payload[1]
    opcode = first & 0x0F
    length = second & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", payload[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", payload[offset : offset + 8])[0]
        offset += 8
    return opcode, payload[offset : offset + length]


class CaptureWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None


def test_build_handshake_response_contains_accept_header() -> None:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    response = build_handshake_response(
        [
            ("upgrade", "websocket"),
            ("connection", "Upgrade"),
            ("sec-websocket-key", key),
            ("sec-websocket-version", "13"),
        ],
        subprotocol=None,
    )
    assert b"101 Switching Protocols" in response
    assert b"sec-websocket-accept" in response.lower()


def test_build_handshake_response_requires_key() -> None:
    with pytest.raises(ValueError, match="Missing Sec-WebSocket-Key"):
        build_handshake_response([("sec-websocket-version", "13")], subprotocol=None)


def test_read_frame_decodes_masked_text() -> None:
    payload = b"hello"
    frame_data = _masked_frame(0x1, payload)

    async def scenario() -> tuple[int, bytes]:
        reader = await make_stream_reader(frame_data)
        frame = await _read_frame(reader, max_size=1024)
        return frame.opcode, frame.payload

    opcode, body = asyncio.run(scenario())
    assert opcode == 0x1
    assert body == payload


def test_read_frame_rejects_unmasked_payloads() -> None:
    frame_data = bytes([0x81, 0x05]) + b"hello"

    async def scenario() -> None:
        reader = await make_stream_reader(frame_data)
        await _read_frame(reader, max_size=1024)

    with pytest.raises(ValueError, match="must be masked"):
        asyncio.run(scenario())


def test_read_frame_rejects_oversized_payloads() -> None:
    payload = b"a" * 16
    frame_data = _masked_frame(0x2, payload)

    async def scenario() -> None:
        reader = await make_stream_reader(frame_data)
        await _read_frame(reader, max_size=8)

    with pytest.raises(ValueError, match="exceeds ws_max_size"):
        asyncio.run(scenario())


def test_read_frame_supports_extended_payload_lengths() -> None:
    payload = b"a" * 130
    frame_data = _masked_frame(0x2, payload)

    async def scenario() -> tuple[int, bytes]:
        reader = await make_stream_reader(frame_data)
        frame = await _read_frame(reader, max_size=1024)
        return frame.opcode, frame.payload

    opcode, body = asyncio.run(scenario())
    assert opcode == 0x2
    assert body == payload


def test_build_websocket_scope_sets_subprotocols_and_scheme() -> None:
    scope = build_websocket_scope(
        target="/ws/chat?room=1",
        headers=_handshake_headers(protocol="chat, superchat"),
        client=("127.0.0.1", 1234),
        server=("127.0.0.1", 8000),
        root_path="/api",
        is_tls=True,
    )

    assert scope["type"] == "websocket"
    assert scope["scheme"] == "wss"
    assert scope["path"] == "/ws/chat"
    assert scope["query_string"] == b"room=1"
    assert scope["subprotocols"] == ["chat", "superchat"]


def test_handle_websocket_rejects_invalid_handshake() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=[("upgrade", "websocket")],
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())

    assert writer.writes
    assert b"400 Bad Request" in b"".join(writer.writes)


def test_handle_websocket_roundtrip_text_and_subprotocol() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    reader_payload = _masked_frame(0x1, b"hello")

    async def app(scope, receive, send):
        assert scope["subprotocols"] == ["chat"]
        await send({"type": "websocket.accept", "subprotocol": "chat"})
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "hello"}
        await send({"type": "websocket.send", "text": "world"})

    async def scenario() -> None:
        reader = await make_stream_reader(reader_payload)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(protocol="chat"),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())

    assert b"101 Switching Protocols" in writer.writes[0]
    assert b"sec-websocket-protocol: chat" in writer.writes[0].lower()
    opcode, payload = _decode_server_frame(writer.writes[1])
    assert opcode == 0x1
    assert payload == b"world"
    close_opcode, _ = _decode_server_frame(writer.writes[2])
    assert close_opcode == 0x8


def test_handle_websocket_replies_to_ping_then_continues() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    reader_payload = _masked_frame(0x9, b"p") + _masked_frame(0x1, b"x")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "x"}

    async def scenario() -> None:
        reader = await make_stream_reader(reader_payload)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())

    pong_opcode, pong_payload = _decode_server_frame(writer.writes[1])
    assert pong_opcode == 0xA
    assert pong_payload == b"p"


def test_handle_websocket_reassembles_fragmented_text_frames() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    reader_payload = _masked_frame(0x1, b"hel", fin=False) + _masked_frame(0x0, b"lo", fin=True)

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "hello"}
        await send({"type": "websocket.close", "code": 1000})

    async def scenario() -> None:
        reader = await make_stream_reader(reader_payload)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())

    close_opcode, close_payload = _decode_server_frame(writer.writes[-1])
    assert close_opcode == 0x8
    assert struct.unpack("!H", close_payload[:2])[0] == 1000


def test_handle_websocket_reports_protocol_error_on_continuation_without_start() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    reader_payload = _masked_frame(0x0, b"orphan")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1002}

    async def scenario() -> None:
        reader = await make_stream_reader(reader_payload)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_handle_websocket_reports_utf8_decode_error_for_text_frames() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    reader_payload = _masked_frame(0x1, b"\xff")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1007}

    async def scenario() -> None:
        reader = await make_stream_reader(reader_payload)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_handle_websocket_send_before_accept_is_rejected() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.send", "text": "oops"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="send before accept"):
        asyncio.run(scenario())


def test_handle_websocket_close_message_writes_code_and_reason() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1001, "reason": "bye"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())

    opcode, payload = _decode_server_frame(writer.writes[-1])
    assert opcode == 0x8
    assert struct.unpack("!H", payload[:2])[0] == 1001
    assert payload[2:] == b"bye"
