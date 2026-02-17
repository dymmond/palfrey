"""WebSocket protocol helper tests."""

from __future__ import annotations

import asyncio
import base64
import os

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.websocket import _read_frame, build_handshake_response, handle_websocket
from tests.helpers import make_stream_reader


def _masked_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    mask = os.urandom(4)
    first = (0x80 if fin else 0x00) | opcode
    second = 0x80 | len(payload)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes([first, second]) + mask + masked


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
    frame = asyncio.run(_read_frame(make_stream_reader(frame_data), max_size=1024))
    assert frame.opcode == 0x1
    assert frame.payload == payload


def test_read_frame_rejects_unmasked_payloads() -> None:
    frame_data = bytes([0x81, 0x05]) + b"hello"
    with pytest.raises(ValueError, match="must be masked"):
        asyncio.run(_read_frame(make_stream_reader(frame_data), max_size=1024))


def test_read_frame_rejects_oversized_payloads() -> None:
    payload = b"a" * 16
    frame_data = _masked_frame(0x2, payload)
    with pytest.raises(ValueError, match="exceeds ws_max_size"):
        asyncio.run(_read_frame(make_stream_reader(frame_data), max_size=8))


def test_handle_websocket_rejects_invalid_handshake() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")

    class Writer:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            return None

    writer = Writer()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})

    asyncio.run(
        handle_websocket(
            app,
            config,
            reader=make_stream_reader(b""),
            writer=writer,
            headers=[("upgrade", "websocket")],
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )
    )

    assert writer.writes
    assert b"400 Bad Request" in b"".join(writer.writes)
