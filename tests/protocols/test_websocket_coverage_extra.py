"""Additional websocket branch-coverage tests."""

from __future__ import annotations

import asyncio
import base64
import os
import runpy
import struct
import types
from collections.abc import Iterable
from typing import cast

import pytest

import palfrey.protocols.websocket as websocket_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.websocket import (
    _encode_frame,
    _flush_websockets_output,
    _http_reason_phrase,
    _wsproto_extra_headers,
    handle_websocket,
)
from tests.helpers import make_stream_reader


def _handshake_headers() -> list[tuple[str, str]]:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    return [
        ("upgrade", "websocket"),
        ("connection", "Upgrade"),
        ("sec-websocket-key", key),
        ("sec-websocket-version", "13"),
    ]


class CaptureWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None


def test_encode_frame_supports_16_and_64_bit_lengths() -> None:
    medium = _encode_frame(0x2, b"a" * 300)
    assert medium[1] == 126
    assert struct.unpack("!H", medium[2:4])[0] == 300

    large = _encode_frame(0x2, b"a" * 70_000)
    assert large[1] == 127
    assert struct.unpack("!Q", large[2:10])[0] == 70_000


def test_http_reason_phrase_uses_fallback_for_unknown_status() -> None:
    assert _http_reason_phrase(418) == "WebSocket Response"


def test_wsproto_extra_headers_skips_invalid_and_coerces_str() -> None:
    result = _wsproto_extra_headers(
        [
            (b"x-a", b"1"),
            ("x-b", "2"),
            ("x-c", 3),
            "invalid",
            ("broken",),
        ]
    )
    assert result == [(b"x-a", b"1"), (b"x-b", b"2"), (b"x-c", b"3")]


def test_flush_websockets_output_accepts_bytes_payload() -> None:
    writer = CaptureWriter()

    class FakeConnection:
        @staticmethod
        def data_to_send() -> bytes:
            return b"bytes-payload"

    asyncio.run(_flush_websockets_output(FakeConnection(), writer))
    assert writer.writes == [b"bytes-payload"]


def _install_fake_wsproto(
    monkeypatch: pytest.MonkeyPatch,
    *,
    initial_events: Iterable[tuple[object, ...]] | None = None,
    events_by_receive_call: dict[int, list[tuple[object, ...]]] | None = None,
    raise_on_receive_calls: set[int] | None = None,
    state: str = "open",
) -> dict[str, object]:
    capture: dict[str, object] = {"sent": []}

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
            self.state = state
            self.receive_calls = 0

        def receive_data(self, data: bytes) -> None:
            self.receive_calls += 1
            if raise_on_receive_calls and self.receive_calls in raise_on_receive_calls:
                raise FakeLocalProtocolError("bad frame")

        def _build_event(self, spec: tuple[object, ...]) -> object:
            kind = str(spec[0])
            if kind == "request":
                return FakeRequest()
            if kind == "ping":
                return FakePing()
            if kind == "pong":
                return FakePong()
            if kind == "text":
                return FakeTextMessage(str(spec[1]), bool(spec[2]))
            if kind == "bytes":
                return FakeBytesMessage(bytes(spec[1]), bool(spec[2]))
            if kind == "close":
                return FakeCloseConnection(int(spec[1]), str(spec[2]))
            if kind == "other":
                return object()
            raise AssertionError(f"Unsupported event spec: {spec!r}")

        def events(self):
            if self.receive_calls == 1:
                return [self._build_event(spec) for spec in initial_events or []]
            return [
                self._build_event(spec)
                for spec in (events_by_receive_call or {}).get(self.receive_calls, [])
            ]

        def send(self, event) -> bytes:
            cast("list[object]", capture["sent"]).append(event)
            if isinstance(event, FakeAcceptConnection):
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

    return capture


def test_wsproto_backend_rejects_bad_initial_receive(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(monkeypatch, raise_on_receive_calls={1})
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

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
    assert b"400 Bad Request" in b"".join(writer.writes)


def test_wsproto_backend_eof_after_accept_disconnects_1005(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1005}

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


def test_wsproto_backend_receive_protocol_error_disconnects_1002(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        raise_on_receive_calls={2},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
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


def test_wsproto_backend_fragmented_text_then_oversized_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={
            2: [("text", "hel", False), ("text", "lo", True)],
            3: [("bytes", b"0123456789", True)],
        },
    )

    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto", ws_max_size=5)
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        first_message = await receive()
        assert first_message == {"type": "websocket.receive", "text": "hello"}
        second_message = await receive()
        assert second_message == {"type": "websocket.disconnect", "code": 1009}

    class ChunkReader:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    async def scenario() -> None:
        reader = ChunkReader([b"a", b"b", b""])
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


def test_wsproto_backend_close_before_accept_returns_http_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])

    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
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
    assert b"403 Forbidden" in b"".join(writer.writes)


def test_wsproto_backend_raises_on_send_before_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.send", "text": "nope"})

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


def test_wsproto_backend_http_rejection_extension_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"denied", "more_body": False})

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
    assert b"denied" in payload


def test_wsproto_backend_http_body_before_start_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.http.response.body", "body": b"nope"})

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

    with pytest.raises(RuntimeError, match="before websocket.http.response.start"):
        asyncio.run(scenario())


def test_wsproto_backend_rejects_http_messages_after_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="after accept"):
        asyncio.run(scenario())


def test_wsproto_backend_close_after_accept_and_receive_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1001, "reason": "bye"})
        message = await receive()
        assert message == {"type": "websocket.disconnect", "code": 1001}

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
    assert writer.writes == [b"ACCEPT", b"CLOSE"]


def test_wsproto_backend_rejects_unknown_asgi_message_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="Unsupported websocket ASGI message type"):
        asyncio.run(scenario())


def test_wsproto_backend_pong_event_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={2: [("pong",), ("text", "ok", True)]},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        message = await receive()
        assert message == {"type": "websocket.receive", "text": "ok"}

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
    assert writer.writes[0] == b"ACCEPT"


def test_wsproto_backend_rejects_when_request_event_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("ping",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        raise AssertionError("ASGI app must not run without a wsproto Request event")

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


def test_wsproto_backend_rejects_multiple_http_response_start_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="Expected ASGI message 'websocket.http.response.body'"):
        asyncio.run(scenario())


def test_wsproto_backend_invalid_http_status_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.http.response.start", "status": 700, "headers": []})

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

    with pytest.raises(RuntimeError, match="Invalid HTTP status code '700'"):
        asyncio.run(scenario())


def test_wsproto_backend_close_before_accept_reports_disconnect_1006(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
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
    assert b"403 Forbidden" in b"".join(writer.writes)


def test_wsproto_backend_http_response_more_body_and_non_bytes_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 403,
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    payload = b"".join(writer.writes).lower()
    assert payload.count(b"content-length:") == 1
    assert payload.count(b"connection: close") == 1
    assert payload.endswith(b"abc")


def test_wsproto_backend_duplicate_accept_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert writer.writes.count(b"ACCEPT") == 1


def test_wsproto_backend_binary_send_path_uses_bytes_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={2: [("close", 1000, "")]},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.send", "bytes": bytearray(b"bin")})
        assert await receive() == {"type": "websocket.disconnect", "code": 1000}

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
    sent = cast("list[object]", capture["sent"])
    assert len(sent) >= 2
    assert getattr(sent[1], "data", b"") == b"bin"


def test_wsproto_backend_rejects_http_response_body_after_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(monkeypatch, initial_events=[("request",)])
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
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
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    with pytest.raises(RuntimeError, match="after accept"):
        asyncio.run(scenario())


def test_wsproto_backend_reassembles_fragmented_binary_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={2: [("bytes", b"a", False), ("bytes", b"b", True)]},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.receive", "bytes": b"ab"}

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


def test_wsproto_backend_invalid_handshake_writes_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(websocket_module, "find_spec", lambda name: object())
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        raise AssertionError("ASGI app must not run on invalid websocket handshake")

    async def scenario() -> None:
        reader = await make_stream_reader(b"")
        await handle_websocket(
            app,
            config,
            reader=reader,
            writer=writer,
            headers=[("upgrade", "websocket"), ("sec-websocket-version", "13")],
            target="/",
            client=("127.0.0.1", 1),
            server=("127.0.0.1", 2),
            is_tls=False,
        )

    asyncio.run(scenario())
    assert b"400 Bad Request" in b"".join(writer.writes)


def test_wsproto_backend_ignores_unknown_events_then_disconnects_on_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={2: [("other",)]},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1005}

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


def test_wsproto_backend_close_event_without_reason_omits_reason_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_wsproto(
        monkeypatch,
        initial_events=[("request",)],
        events_by_receive_call={2: [("close", 1000, "")]},
    )
    config = PalfreyConfig(app="tests.fixtures.apps:websocket_app", ws="wsproto")
    writer = CaptureWriter()

    async def app(scope, receive, send):
        await send({"type": "websocket.accept"})
        assert await receive() == {"type": "websocket.disconnect", "code": 1000}

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


def test_main_module_invokes_cli_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    fake_cli = types.SimpleNamespace(main=lambda: called.append(True))
    monkeypatch.setitem(__import__("sys").modules, "palfrey.cli", fake_cli)
    runpy.run_module("palfrey.__main__", run_name="__main__")
    assert called == [True]
