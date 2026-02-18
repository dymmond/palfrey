"""WebSocket protocol helper tests."""

from __future__ import annotations

import asyncio
import base64
import os
import struct
import types
from typing import cast

import pytest

import palfrey.protocols.websocket as websocket_module
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


def _parse_http_response_headers(payload: bytes) -> dict[str, str]:
    head = payload.split(b"\r\n\r\n", 1)[0]
    lines = head.split(b"\r\n")[1:]
    headers: dict[str, str] = {}
    for line in lines:
        if b":" not in line:
            continue
        name, value = line.split(b":", 1)
        headers[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    return headers


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
    assert scope["path"] == "/api/ws/chat"
    assert scope["raw_path"] == b"/api/ws/chat"
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


def test_handle_websocket_close_before_accept_returns_403() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.close", "code": 1000})

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
    assert b"403 Forbidden" in writer.writes[0]


def test_handle_websocket_http_response_extension_returns_http_reply() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "websocket.http.response.body",
                "body": b"denied",
                "more_body": False,
            }
        )

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
    payload = b"".join(writer.writes)
    assert b"HTTP/1.1 401" in payload
    assert b"content-type: text/plain" in payload.lower()
    assert payload.endswith(b"denied")


def test_handle_websocket_dispatches_wsproto_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()
    called: list[str] = []

    async def fake_backend(*args, **kwargs):
        called.append("wsproto")

    monkeypatch.setattr(websocket_module, "_handle_websocket_wsproto_backend", fake_backend)

    async def app(scope, receive, send):
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert called == ["wsproto"]


def test_handle_websocket_dispatches_websockets_sansio_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()
    called: list[str] = []

    async def fake_backend(*args, **kwargs):
        called.append("sansio")

    monkeypatch.setattr(
        websocket_module,
        "_handle_websocket_websockets_sansio_backend",
        fake_backend,
    )

    async def app(scope, receive, send):
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert called == ["sansio"]


def test_handle_websocket_dispatches_websockets_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets")
    writer = CaptureWriter()
    called: list[str] = []

    async def fake_backend(*args, **kwargs):
        called.append("websockets")

    monkeypatch.setattr(websocket_module, "_handle_websocket_websockets_backend", fake_backend)

    async def app(scope, receive, send):
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert called == ["websockets"]


def test_wsproto_backend_requires_wsproto_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()
    monkeypatch.setattr(websocket_module, "find_spec", lambda name: None)

    async def app(scope, receive, send):
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="requires the 'wsproto' package"):
        asyncio.run(scenario())


def test_websockets_sansio_backend_requires_websockets_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()
    monkeypatch.setattr(websocket_module, "find_spec", lambda name: None)

    async def app(scope, receive, send):
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="requires the 'websockets' package"):
        asyncio.run(scenario())


def test_wsproto_backend_roundtrip_with_fake_wsproto(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app",
        ws="wsproto",
        headers=[("x-config", "1")],
        date_header=False,
    )
    writer = CaptureWriter()
    accept_events: list[object] = []

    class FakeLocalProtocolError(Exception):
        pass

    class FakeRemoteProtocolError(Exception):
        pass

    class FakeConnectionType:
        SERVER = "server"

    class FakeConnectionState:
        REMOTE_CLOSING = "remote-closing"

    class FakeRequest:
        pass

    class FakePing:
        def response(self):
            return FakePong()

    class FakePong:
        pass

    class FakeMessage:
        def __init__(self, data):
            self.data = data

    class FakeTextMessage:
        def __init__(self, data: str, message_finished: bool) -> None:
            self.data = data
            self.message_finished = message_finished

    class FakeBytesMessage:
        def __init__(self, data: bytes, message_finished: bool) -> None:
            self.data = data
            self.message_finished = message_finished

    class FakeCloseConnection:
        def __init__(self, code: int, reason: str) -> None:
            self.code = code
            self.reason = reason

        def response(self):
            return FakeCloseConnection(self.code, self.reason)

    class FakeAcceptConnection:
        def __init__(self, subprotocol=None, extensions=None, extra_headers=None) -> None:
            self.subprotocol = subprotocol
            self.extensions = extensions
            self.extra_headers = extra_headers

    class FakePerMessageDeflate:
        pass

    class FakeWSConnection:
        def __init__(self, connection_type) -> None:
            self.connection_type = connection_type
            self.state = "open"
            self.receive_calls = 0

        def receive_data(self, data: bytes) -> None:
            self.receive_calls += 1

        def events(self):
            if self.receive_calls == 1:
                return [FakeRequest()]
            if self.receive_calls == 2:
                return [FakeTextMessage("hello", True)]
            return []

        def send(self, event) -> bytes:
            if isinstance(event, FakeAcceptConnection):
                accept_events.append(event)
                return b"ACCEPT"
            if isinstance(event, FakeMessage):
                payload = event.data.encode("utf-8") if isinstance(event.data, str) else event.data
                return b"MSG:" + payload
            if isinstance(event, FakeCloseConnection):
                return b"CLOSE"
            if isinstance(event, FakePong):
                return b"PONG"
            return b"EVENT"

    wsproto_module = types.SimpleNamespace(
        WSConnection=FakeWSConnection,
        ConnectionType=FakeConnectionType,
    )
    events_module = types.SimpleNamespace(
        Request=FakeRequest,
        Ping=FakePing,
        Pong=FakePong,
        Message=FakeMessage,
        TextMessage=FakeTextMessage,
        BytesMessage=FakeBytesMessage,
        CloseConnection=FakeCloseConnection,
        AcceptConnection=FakeAcceptConnection,
    )
    connection_module = types.SimpleNamespace(ConnectionState=FakeConnectionState)
    extensions_module = types.SimpleNamespace(PerMessageDeflate=FakePerMessageDeflate)
    utilities_module = types.SimpleNamespace(
        LocalProtocolError=FakeLocalProtocolError,
        RemoteProtocolError=FakeRemoteProtocolError,
    )
    modules = {
        "wsproto": wsproto_module,
        "wsproto.events": events_module,
        "wsproto.connection": connection_module,
        "wsproto.extensions": extensions_module,
        "wsproto.utilities": utilities_module,
    }

    monkeypatch.setattr(websocket_module, "find_spec", lambda name: object())
    monkeypatch.setattr(websocket_module.importlib, "import_module", lambda name: modules[name])

    async def app(scope, receive, send):
        await send(
            {
                "type": "websocket.accept",
                "subprotocol": "chat",
                "headers": [(b"x-app", b"2")],
            }
        )
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "hello"}
        await send({"type": "websocket.send", "text": "world"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"client-payload")
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
    assert writer.writes == [b"ACCEPT", b"MSG:world", b"CLOSE"]
    assert len(accept_events) == 1
    assert (b"server", b"palfrey") in accept_events[0].extra_headers
    assert (b"x-config", b"1") in accept_events[0].extra_headers
    assert (b"x-app", b"2") in accept_events[0].extra_headers


def test_wsproto_backend_processes_ping_and_close_events(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    class FakeLocalProtocolError(Exception):
        pass

    class FakeRemoteProtocolError(Exception):
        pass

    class FakeConnectionType:
        SERVER = "server"

    class FakeConnectionState:
        REMOTE_CLOSING = "remote-closing"

    class FakeRequest:
        pass

    class FakePong:
        pass

    class FakePing:
        def response(self):
            return FakePong()

    class FakeMessage:
        def __init__(self, data):
            self.data = data

    class FakeTextMessage:
        def __init__(self, data: str, message_finished: bool) -> None:
            self.data = data
            self.message_finished = message_finished

    class FakeBytesMessage:
        def __init__(self, data: bytes, message_finished: bool) -> None:
            self.data = data
            self.message_finished = message_finished

    class FakeCloseConnection:
        def __init__(self, code: int, reason: str) -> None:
            self.code = code
            self.reason = reason

        def response(self):
            return FakeCloseConnection(self.code, self.reason)

    class FakeAcceptConnection:
        def __init__(self, subprotocol=None, extensions=None, extra_headers=None) -> None:
            self.subprotocol = subprotocol
            self.extensions = extensions
            self.extra_headers = extra_headers

    class FakeWSConnection:
        def __init__(self, connection_type) -> None:
            self.connection_type = connection_type
            self.state = FakeConnectionState.REMOTE_CLOSING
            self.receive_calls = 0

        def receive_data(self, data: bytes) -> None:
            self.receive_calls += 1

        def events(self):
            if self.receive_calls == 1:
                return [FakeRequest()]
            if self.receive_calls == 2:
                return [FakePing(), FakeCloseConnection(1001, "bye")]
            return []

        def send(self, event) -> bytes:
            if isinstance(event, FakeAcceptConnection):
                return b"ACCEPT"
            if isinstance(event, FakePong):
                return b"PONG"
            if isinstance(event, FakeCloseConnection):
                return b"CLOSE"
            if isinstance(event, FakeMessage):
                return b"MSG"
            return b"EVENT"

    wsproto_module = types.SimpleNamespace(
        WSConnection=FakeWSConnection,
        ConnectionType=FakeConnectionType,
    )
    events_module = types.SimpleNamespace(
        Request=FakeRequest,
        Ping=FakePing,
        Pong=FakePong,
        Message=FakeMessage,
        TextMessage=FakeTextMessage,
        BytesMessage=FakeBytesMessage,
        CloseConnection=FakeCloseConnection,
        AcceptConnection=FakeAcceptConnection,
    )
    connection_module = types.SimpleNamespace(ConnectionState=FakeConnectionState)
    extensions_module = types.SimpleNamespace()
    utilities_module = types.SimpleNamespace(
        LocalProtocolError=FakeLocalProtocolError,
        RemoteProtocolError=FakeRemoteProtocolError,
    )
    modules = {
        "wsproto": wsproto_module,
        "wsproto.events": events_module,
        "wsproto.connection": connection_module,
        "wsproto.extensions": extensions_module,
        "wsproto.utilities": utilities_module,
    }

    monkeypatch.setattr(websocket_module, "find_spec", lambda name: object())
    monkeypatch.setattr(websocket_module.importlib, "import_module", lambda name: modules[name])

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1001, "reason": "bye"}

    async def scenario() -> None:
        reader = await make_stream_reader(b"client-payload")
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
    assert writer.writes[:3] == [b"ACCEPT", b"PONG", b"CLOSE"]


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


def test_handle_websocket_accept_includes_default_and_custom_headers() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app",
        ws="none",
        headers=[("x-extra", "one")],
    )
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
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    headers = _parse_http_response_headers(writer.writes[0])
    assert headers["server"] == "palfrey"
    assert headers["x-extra"] == "one"
    assert "date" in headers


def test_handle_websocket_accept_respects_server_and_date_toggles() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app",
        ws="none",
        server_header=False,
        date_header=False,
        headers=[("x-extra", "one")],
    )
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
            headers=_handshake_headers(),
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    headers = _parse_http_response_headers(writer.writes[0])
    assert "server" not in headers
    assert "date" not in headers
    assert headers["x-extra"] == "one"


def _install_fake_websockets_sansio(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_batches: list[list[tuple[object, ...]]],
    raise_on_receive_call: set[int] | None = None,
    accept_status: int = 101,
    parser_exc_on_receive_call: int | None = None,
    parser_close_code: int = 1002,
    parser_close_reason: str = "",
) -> dict[str, object]:
    state: dict[str, object] = {"instances": [], "responses": []}

    class Opcode:
        CONT = 0x0
        TEXT = 0x1
        BINARY = 0x2
        CLOSE = 0x8
        PING = 0x9
        PONG = 0xA

    class Frame:
        def __init__(self, opcode: int, data: bytes, fin: bool = True) -> None:
            self.opcode = opcode
            self.data = data
            self.fin = fin

    class Request:
        def __init__(self, path: str) -> None:
            self.path = path

    class FakeResponse:
        def __init__(self, status_code: int, body: str = "") -> None:
            self.status_code = status_code
            self.headers: dict[str, str] = {}
            self.body = body

    class FakeInvalidStateError(Exception):
        pass

    class FakeProtocolError(Exception):
        pass

    class FakePayloadTooBigError(Exception):
        pass

    class FakePerMessageDeflateFactory:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    def _build_events(specs: list[tuple[object, ...]]) -> list[object]:
        events: list[object] = []
        for spec in specs:
            kind = str(spec[0])
            if kind == "request":
                events.append(Request(str(spec[1])))
            elif kind == "text":
                fin = bool(spec[2]) if len(spec) > 2 else True
                events.append(Frame(Opcode.TEXT, bytes(spec[1]), fin))
            elif kind == "binary":
                fin = bool(spec[2]) if len(spec) > 2 else True
                events.append(Frame(Opcode.BINARY, bytes(spec[1]), fin))
            elif kind == "cont":
                fin = bool(spec[2]) if len(spec) > 2 else True
                events.append(Frame(Opcode.CONT, bytes(spec[1]), fin))
            elif kind == "ping":
                events.append(Frame(Opcode.PING, bytes(spec[1]), True))
            elif kind == "close":
                events.append(Frame(Opcode.CLOSE, b"", True))
            elif kind == "invalid":
                events.append(Frame(0x3, bytes(spec[1]), True))
        return events

    class FakeServerProtocol:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self._events = [_build_events(batch) for batch in event_batches]
            self._out: list[bytes] = []
            self._receive_calls = 0
            self.parser_exc = None
            self.close_sent = None
            self.close_rcvd = None
            cast("list[object]", state["instances"]).append(self)

        def receive_data(self, data: bytes) -> None:
            self._receive_calls += 1
            if raise_on_receive_call and self._receive_calls in raise_on_receive_call:
                raise FakeProtocolError("bad frame")
            if (
                parser_exc_on_receive_call is not None
                and self._receive_calls == parser_exc_on_receive_call
            ):
                self.parser_exc = FakeProtocolError("parser error")
                self.close_sent = types.SimpleNamespace(
                    code=parser_close_code,
                    reason=parser_close_reason,
                )

        def events_received(self) -> list[object]:
            if self._events:
                events = self._events.pop(0)
                for event in events:
                    if isinstance(event, Frame) and event.opcode == Opcode.CLOSE:
                        self.close_rcvd = types.SimpleNamespace(code=1001, reason="bye")
                return events
            return []

        def accept(self, request: Request) -> FakeResponse:
            return FakeResponse(accept_status)

        def reject(self, status: int, text: str) -> FakeResponse:
            return FakeResponse(int(status), text)

        def send_response(self, response: FakeResponse) -> None:
            cast("list[object]", state["responses"]).append(response)
            payload = f"RESP:{response.status_code}".encode("ascii")
            if response.body:
                payload += b":" + response.body.encode("utf-8")
            self._out.append(payload)

        def data_to_send(self) -> list[bytes]:
            out = list(self._out)
            self._out.clear()
            return out

        def send_close(self, code: int, reason: str) -> None:
            self.close_sent = types.SimpleNamespace(code=code, reason=reason)
            self._out.append(f"CLOSE:{code}:{reason}".encode())

        def send_text(self, data: bytes) -> None:
            self._out.append(b"TEXT:" + data)

        def send_binary(self, data: bytes) -> None:
            self._out.append(b"BINARY:" + data)

    modules = {
        "websockets.server": types.SimpleNamespace(ServerProtocol=FakeServerProtocol),
        "websockets.frames": types.SimpleNamespace(Frame=Frame, Opcode=Opcode),
        "websockets.exceptions": types.SimpleNamespace(
            InvalidState=FakeInvalidStateError,
            ProtocolError=FakeProtocolError,
            PayloadTooBig=FakePayloadTooBigError,
        ),
        "websockets.extensions.permessage_deflate": types.SimpleNamespace(
            ServerPerMessageDeflateFactory=FakePerMessageDeflateFactory
        ),
    }

    monkeypatch.setattr(websocket_module, "find_spec", lambda name: object())
    monkeypatch.setattr(websocket_module.importlib, "import_module", lambda name: modules[name])
    return state


def test_websockets_sansio_backend_accepts_and_roundtrips_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app",
        ws="websockets-sansio",
        headers=[("x-config", "1")],
        date_header=False,
    )
    writer = CaptureWriter()

    state = _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[
            [("request", "/room")],
            [("text", b"hello", True)],
        ],
    )

    async def app(scope, receive, send):
        connect = await receive()
        assert connect == {"type": "websocket.connect"}
        assert scope["http_version"] == "1.1"
        assert "websocket.http.response" in scope["extensions"]
        await send(
            {
                "type": "websocket.accept",
                "subprotocol": "chat",
                "headers": [(b"x-extra", b"1")],
            }
        )
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "hello"}
        await send({"type": "websocket.send", "text": "world"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"client-payload")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(protocol="chat"),
            target="/room",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    payload = b"".join(writer.writes)
    assert b"RESP:101" in payload
    assert b"TEXT:world" in payload
    assert b"CLOSE:1000:" in payload
    responses = cast("list[object]", state["responses"])
    assert responses
    headers = responses[0].headers
    assert headers["server"] == "palfrey"
    assert headers["x-config"] == "1"
    assert headers["x-extra"] == "1"


def test_websockets_sansio_backend_supports_http_response_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(monkeypatch, event_batches=[[("request", "/deny")]])

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 401,
                "headers": [(b"x-reason", b"denied")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"denied"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/deny",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    payload = b"".join(writer.writes)
    assert b"RESP:401:denied" in payload


def test_websockets_sansio_backend_reports_disconnect_on_parser_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[[("request", "/")]],
        raise_on_receive_call={2},
    )

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1002}

    async def scenario() -> None:
        reader = await make_stream_reader(b"x")
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
    assert b"RESP:101" in b"".join(writer.writes)


def test_websockets_sansio_backend_falls_back_to_500_on_invalid_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(monkeypatch, event_batches=[[("request", "/oops")]])

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.http.response.start", "status": 700})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/oops",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"RESP:500:Internal Server Error" in b"".join(writer.writes)


def test_websockets_sansio_backend_processes_ping_and_close_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[
            [("request", "/")],
            [("ping", b"p"), ("close", b"")],
        ],
    )

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1001, "reason": "bye"}

    async def scenario() -> None:
        reader = await make_stream_reader(b"x")
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
    assert b"RESP:101" in b"".join(writer.writes)


def test_websockets_sansio_backend_reassembles_fragmented_text_and_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[
            [("request", "/fragment")],
            [("text", b"hel", False), ("cont", b"lo", True)],
            [("binary", b"\x00", False), ("cont", b"\x01", True)],
        ],
    )

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        text_message = await receive()
        assert text_message == {"type": "websocket.receive", "text": "hello"}
        binary_message = await receive()
        assert binary_message == {"type": "websocket.receive", "bytes": b"\x00\x01"}

    async def scenario() -> None:
        reader = await make_stream_reader(b"ab")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/fragment",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"RESP:101" in b"".join(writer.writes)


def test_websockets_sansio_backend_rejects_invalid_continuation_and_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[
            [("request", "/bad")],
            [("cont", b"orphan", True)],
        ],
    )

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1002}

    async def scenario() -> None:
        reader = await make_stream_reader(b"x")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/bad",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"CLOSE:1002:unexpected continuation frame" in b"".join(writer.writes)

    writer = CaptureWriter()
    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[
            [("request", "/bad-utf8")],
            [("text", b"\xff", True)],
        ],
    )

    async def utf8_app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1007}

    async def utf8_scenario() -> None:
        reader = await make_stream_reader(b"x")
        await handle_websocket(
            utf8_app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/bad-utf8",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(utf8_scenario())
    assert b"CLOSE:1007:invalid UTF-8 payload" in b"".join(writer.writes)


def _install_fake_websockets_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    recv_values: list[str | bytes] | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "sent": [],
        "closed": None,
        "accepted_response": None,
        "request_response": None,
        "lost": False,
    }

    class FakeConnectionClosedError(Exception):
        pass

    class FakeResponse:
        def __init__(self, status: int, body: str = "") -> None:
            self.status = status
            self.body = body
            self.headers: dict[str, str] = {}

    class FakeServerProtocol:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeServerConnection:
        def __init__(self, protocol, server, *, ping_interval, ping_timeout, max_queue) -> None:
            self.protocol = protocol
            self.server = server
            self.ping_interval = ping_interval
            self.ping_timeout = ping_timeout
            self.max_queue = max_queue
            self.close_code = 1000
            self.close_reason = ""
            self._recv_values = list(recv_values or [])

        def connection_made(self, transport) -> None:
            self.transport = transport

        def data_received(self, data: bytes) -> None:
            return None

        def connection_lost(self, exc) -> None:
            state["lost"] = True

        async def recv(self):
            if self._recv_values:
                return self._recv_values.pop(0)
            raise FakeConnectionClosedError()

        async def send(self, payload) -> None:
            cast("list[object]", state["sent"]).append(payload)

        async def close(self, code: int, reason: str) -> None:
            state["closed"] = (code, reason)

        def respond(self, status: int, body: str) -> FakeResponse:
            return FakeResponse(status, body)

        async def handshake(self, *, process_request, process_response, server_header=None) -> None:
            request = object()
            maybe_response = await process_request(self, request)
            if maybe_response is not None:
                state["request_response"] = maybe_response
                return
            response = FakeResponse(101, "")
            response = await process_response(self, request, response)
            state["accepted_response"] = response

    class FakePerMessageDeflateFactory:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    modules = {
        "websockets.server": types.SimpleNamespace(ServerProtocol=FakeServerProtocol),
        "websockets.asyncio.server": types.SimpleNamespace(ServerConnection=FakeServerConnection),
        "websockets.exceptions": types.SimpleNamespace(ConnectionClosed=FakeConnectionClosedError),
        "websockets.extensions.permessage_deflate": types.SimpleNamespace(
            ServerPerMessageDeflateFactory=FakePerMessageDeflateFactory
        ),
    }

    monkeypatch.setattr(websocket_module, "find_spec", lambda name: object())
    monkeypatch.setattr(websocket_module.importlib, "import_module", lambda name: modules[name])
    return state


class CaptureWriterWithTransport(CaptureWriter):
    def __init__(self) -> None:
        super().__init__()
        self.transport = object()


def test_websockets_backend_accept_headers_and_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app",
        ws="websockets",
        headers=[("x-config", "1")],
        date_header=False,
    )
    writer = CaptureWriterWithTransport()
    state = _install_fake_websockets_backend(monkeypatch, recv_values=["hello"])

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send(
            {
                "type": "websocket.accept",
                "subprotocol": "chat",
                "headers": [(b"x-app", b"2")],
            }
        )
        assert await receive() == {"type": "websocket.receive", "text": "hello"}
        await send({"type": "websocket.send", "text": "world"})

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
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
    accepted = state["accepted_response"]
    assert accepted is not None
    headers = accepted.headers
    assert headers["server"] == "palfrey"
    assert headers["x-config"] == "1"
    assert headers["x-app"] == "2"
    assert headers["Sec-WebSocket-Protocol"] == "chat"
    assert cast("list[object]", state["sent"]) == ["world"]
    assert state["closed"] == (1000, "")


def test_websockets_backend_supports_http_rejection_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:websocket_app", ws="websockets", date_header=False
    )
    writer = CaptureWriterWithTransport()
    state = _install_fake_websockets_backend(monkeypatch)

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 401,
                "headers": [(b"x-reason", b"denied")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"denied"})

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
    rejected = state["request_response"]
    assert rejected is not None
    assert rejected.status == 401
    assert rejected.body == "denied"
    assert rejected.headers["x-reason"] == "denied"


def test_websockets_backend_close_before_accept_reports_disconnect_1006(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets")
    writer = CaptureWriterWithTransport()
    state = _install_fake_websockets_backend(monkeypatch)

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.close"})
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    rejected = state["request_response"]
    assert rejected is not None
    assert rejected.status == 403


def test_websockets_backend_rejects_messages_after_close(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets")
    writer = CaptureWriterWithTransport()
    _install_fake_websockets_backend(monkeypatch)

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.close"})
        with pytest.raises(RuntimeError, match="Unexpected ASGI message"):
            await send({"type": "websocket.send", "text": "late"})

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


def test_websockets_sansio_backend_rejects_non_101_accept_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[[("request", "/deny")]],
        accept_status=403,
    )

    async def app(scope, receive, send):
        raise AssertionError("ASGI app must not run when upgrade response is not 101")

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=_handshake_headers(),
            target="/deny",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"RESP:403" in b"".join(writer.writes)


def test_websockets_sansio_backend_rejects_when_request_event_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[[("text", b"hello", True)]],
    )

    async def app(scope, receive, send):
        raise AssertionError("ASGI app must not run without a websocket request event")

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
    assert b"400 Bad Request" in b"".join(writer.writes)


def test_websockets_sansio_backend_parser_exception_includes_disconnect_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="websockets-sansio")
    writer = CaptureWriter()

    _install_fake_websockets_sansio(
        monkeypatch,
        event_batches=[[("request", "/")]],
        parser_exc_on_receive_call=2,
        parser_close_code=1011,
        parser_close_reason="internal",
    )

    async def app(scope, receive, send):
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})
        assert await receive() == {
            "type": "websocket.disconnect",
            "code": 1011,
            "reason": "internal",
        }

    async def scenario() -> None:
        reader = await make_stream_reader(b"x")
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
