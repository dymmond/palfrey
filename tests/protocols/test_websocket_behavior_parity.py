"""WebSocket behavior parity tests for handshake and frame handling."""

from __future__ import annotations

import asyncio
import base64
import os
import struct

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.websocket import (
    _read_frame,
    _validate_handshake,
    build_handshake_response,
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
    masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + mask + masked_payload


def _handshake_headers(key: str | None = None) -> list[tuple[str, str]]:
    token = key or base64.b64encode(os.urandom(16)).decode("ascii")
    return [
        ("upgrade", "websocket"),
        ("connection", "Upgrade"),
        ("sec-websocket-key", token),
        ("sec-websocket-version", "13"),
    ]


class CaptureWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None


def _decode_frame_header(payload: bytes) -> tuple[int, bytes]:
    opcode = payload[0] & 0x0F
    length = payload[1] & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", payload[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", payload[offset : offset + 8])[0]
        offset += 8
    return opcode, payload[offset : offset + length]


def test_validate_handshake_requires_version_13() -> None:
    headers = _handshake_headers()
    headers[-1] = ("sec-websocket-version", "12")
    with pytest.raises(ValueError, match="Unsupported websocket version"):
        _validate_handshake(headers)


def test_validate_handshake_requires_key() -> None:
    with pytest.raises(ValueError, match="Missing Sec-WebSocket-Key"):
        _validate_handshake([("sec-websocket-version", "13")])


def test_validate_handshake_rejects_invalid_base64_key() -> None:
    with pytest.raises(ValueError, match="Invalid Sec-WebSocket-Key"):
        _validate_handshake(_handshake_headers(key="!!!not-base64!!!"))


def test_validate_handshake_rejects_invalid_key_length() -> None:
    short_key = base64.b64encode(b"short").decode("ascii")
    with pytest.raises(ValueError, match="Invalid Sec-WebSocket-Key length"):
        _validate_handshake(_handshake_headers(key=short_key))


def test_build_handshake_response_includes_subprotocol_when_selected() -> None:
    response = build_handshake_response(_handshake_headers(), subprotocol="chat")
    assert b"sec-websocket-protocol: chat" in response.lower()


def test_build_handshake_response_omits_subprotocol_when_unset() -> None:
    response = build_handshake_response(_handshake_headers(), subprotocol=None)
    assert b"sec-websocket-protocol" not in response.lower()


def test_read_frame_supports_16bit_length() -> None:
    payload = b"a" * 300

    async def scenario() -> bytes:
        reader = await make_stream_reader(_masked_frame(0x2, payload))
        frame = await _read_frame(reader, max_size=1024)
        return frame.payload

    assert asyncio.run(scenario()) == payload


def test_read_frame_supports_64bit_length_marker() -> None:
    payload = b"a" * 70_000

    async def scenario() -> int:
        reader = await make_stream_reader(_masked_frame(0x2, payload))
        frame = await _read_frame(reader, max_size=80_000)
        return len(frame.payload)

    assert asyncio.run(scenario()) == len(payload)


def test_handle_websocket_binary_roundtrip() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    incoming = _masked_frame(0x2, b"\x00\x01\x02")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.receive", "bytes": b"\x00\x01\x02"}
        await send({"type": "websocket.send", "bytes": b"\x03\x04"})

    async def scenario() -> None:
        reader = await make_stream_reader(incoming)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())

    opcode, payload = _decode_frame_header(writer.writes[1])
    assert opcode == 0x2
    assert payload == b"\x03\x04"


def test_handle_websocket_disconnect_on_invalid_data_opcode() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    incoming = _masked_frame(0x3, b"invalid-opcode")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1002}

    async def scenario() -> None:
        reader = await make_stream_reader(incoming)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_handle_websocket_reports_disconnect_code_from_close_frame() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()
    close_payload = struct.pack("!H", 1001)
    incoming = _masked_frame(0x8, close_payload)

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1001}

    async def scenario() -> None:
        reader = await make_stream_reader(incoming)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_handle_websocket_sends_close_if_app_returns_after_accept() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        return None

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())

    close_opcode, _ = _decode_frame_header(writer.writes[-1])
    assert close_opcode == 0x8


def test_core_backend_close_before_accept_reports_disconnect_1006() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.close", "code": 1001, "reason": "bye"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1006}

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"403 Forbidden" in writer.writes[0]


def test_core_backend_rejects_multiple_http_response_start_events() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.http.response.start", "status": 404, "headers": []})
        await send({"type": "websocket.http.response.start", "status": 404, "headers": []})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="Expected ASGI message 'websocket.http.response.body'"):
        asyncio.run(scenario())


def test_core_backend_fragmented_text_invalid_utf8_disconnects_1007() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()
    incoming = _masked_frame(0x1, b"\xff", fin=False) + _masked_frame(0x0, b"", fin=True)

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1007}

    async def scenario() -> None:
        reader = await make_stream_reader(incoming)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_core_backend_http_response_body_cast_and_header_passthrough() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 400,
                "headers": [(b"content-length", b"3"), (b"connection", b"close")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"a", "more_body": True})
        await send({"type": "websocket.http.response.body", "body": bytearray(b"bc")})
        assert await receive() == {"type": "websocket.disconnect", "code": 1006}

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())
    payload = b"".join(writer.writes).lower()
    assert payload.count(b"content-length:") == 1
    assert payload.count(b"connection: close") == 1
    assert payload.endswith(b"abc")


def test_core_backend_fragmented_binary_roundtrip() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()
    incoming = (
        _masked_frame(0x2, b"\x00", fin=False)
        + _masked_frame(0x0, b"\x01", fin=False)
        + _masked_frame(0x0, b"\x02", fin=True)
    )

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.receive", "bytes": b"\x00\x01\x02"}

    async def scenario() -> None:
        reader = await make_stream_reader(incoming)
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())


def test_core_backend_duplicate_accept_is_ignored() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.accept"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"101 Switching Protocols" in writer.writes[0]


def test_core_backend_rejects_http_response_events_after_accept() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.http.response.start", "status": 401})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="after accept"):
        asyncio.run(scenario())


def test_core_backend_rejects_unknown_asgi_message_type() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.unknown"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1234),
            server=("127.0.0.1", 8000),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="Unsupported websocket ASGI message type"):
        asyncio.run(scenario())
