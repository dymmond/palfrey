"""WebSocket behavior parity tests for handshake and frame handling."""

from __future__ import annotations

import asyncio
import base64
import os
import struct

import pytest

import palfrey.protocols.websocket as websocket_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.websocket import (
    _encode_frame,
    _read_frame,
    _try_parse_frame_from_buffer,
    _validate_handshake,
    _validate_handshake_from_map,
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


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({}, "Unsupported websocket version"),
        ({"sec-websocket-version": "13"}, "Missing Sec-WebSocket-Key"),
        (
            {"sec-websocket-version": "13", "sec-websocket-key": "not-base64"},
            "Invalid Sec-WebSocket-Key",
        ),
        (
            {
                "sec-websocket-version": "13",
                "sec-websocket-key": base64.b64encode(b"short").decode("ascii"),
            },
            "Invalid Sec-WebSocket-Key length",
        ),
    ],
)
def test_validate_handshake_from_map_rejects_invalid_inputs(
    headers: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _validate_handshake_from_map(headers)


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


def test_encode_frame_supports_small_payloads() -> None:
    payload = b"hello"
    frame = _encode_frame(0x1, payload)
    assert frame[:2] == bytes([0x81, len(payload)])
    assert frame[2:] == payload


def test_write_frame_uses_writelines_when_available() -> None:
    class Writer:
        def __init__(self) -> None:
            self.chunks: list[tuple[bytes, bytes]] = []

        def writelines(self, chunks) -> None:
            self.chunks.append((chunks[0], chunks[1]))

        def write(self, data: bytes) -> None:
            raise AssertionError("write should not be used when writelines is available")

    writer = Writer()
    websocket_module._write_frame(writer, 0x2, b"a" * 300)
    header, payload = writer.chunks[0]
    assert header[0] == 0x82
    assert header[1] == 126
    assert struct.unpack("!H", header[2:4])[0] == 300
    assert payload == b"a" * 300


def test_write_frame_supports_64bit_length_path() -> None:
    class Writer:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def write(self, data: bytes) -> None:
            self.writes.append(data)

    payload = b"a" * 70_000
    writer = Writer()
    websocket_module._write_frame(writer, 0x2, payload)
    written = writer.writes[0]
    assert written[0] == 0x82
    assert written[1] == 127
    assert struct.unpack("!Q", written[2:10])[0] == len(payload)


def test_try_parse_frame_from_buffer_handles_partial_extended_lengths() -> None:
    frame_16 = _masked_frame(0x2, b"a" * 300)
    partial_16 = bytearray(frame_16[:3])
    assert _try_parse_frame_from_buffer(partial_16, max_size=1024) is None

    frame_64 = _masked_frame(0x2, b"a" * 70_000)
    partial_64 = bytearray(frame_64[:9])
    assert _try_parse_frame_from_buffer(partial_64, max_size=80_000) is None


def test_try_parse_frame_from_buffer_rejects_unmasked_payload() -> None:
    unmasked = bytearray(bytes([0x81, 0x01]) + b"a")
    with pytest.raises(ValueError, match="must be masked"):
        _try_parse_frame_from_buffer(unmasked, max_size=1024)


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


def test_core_backend_receive_eof_disconnects_1006_before_accept() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
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


def test_core_backend_receive_eof_disconnects_1005_after_accept() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1005}

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


def test_core_backend_ping_drain_respects_high_watermark() -> None:
    class HighWaterWriter:
        class _Transport:
            @staticmethod
            def get_write_buffer_size() -> int:
                return 300_000

        def __init__(self) -> None:
            self.transport = self._Transport()
            self.writes: list[bytes] = []
            self.drain_calls = 0

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            self.drain_calls += 1

    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = HighWaterWriter()
    incoming = _masked_frame(0x9, b"ping")

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.disconnect", "code": 1006}

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
    assert writer.drain_calls >= 1
    assert any((payload[0] & 0x0F) == 0xA for payload in writer.writes)


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


def test_core_backend_close_frame_without_code_defaults_to_1000() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()
    incoming = _masked_frame(0x8, b"")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1000}

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


def test_core_backend_ignores_pong_then_reads_next_frame() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()
    incoming = _masked_frame(0xA, b"pong") + _masked_frame(0x1, b"ok")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.receive", "text": "ok"}

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


def test_core_backend_disconnects_on_unknown_control_opcode() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()
    incoming = _masked_frame(0xB, b"x")

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1002}

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


def test_core_backend_rejects_http_response_body_after_accept() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.http.response.body", "body": b"x"})

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


def test_core_backend_rejects_http_response_body_before_start() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="none")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.http.response.body", "body": b"x"})

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

    with pytest.raises(RuntimeError, match="before websocket.http.response.start"):
        asyncio.run(scenario())
