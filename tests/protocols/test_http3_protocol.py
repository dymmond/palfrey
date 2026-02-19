from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import palfrey.protocols.http3 as http3_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPRequest, HTTPResponse


def test_decode_request_headers_for_http3() -> None:
    method, target, headers = http3_module._decode_request_headers(
        [
            (b":method", b"GET"),
            (b":path", b"/items?limit=2"),
            (b":authority", b"api.example.com"),
            (b"user-agent", b"test"),
        ]
    )

    assert method == "GET"
    assert target == "/items?limit=2"
    assert ("user-agent", "test") in headers
    assert ("host", "api.example.com") in headers


def test_encode_response_headers_for_http3() -> None:
    response = HTTPResponse(
        status=204,
        headers=[(b"connection", b"close"), (b"x-id", b"123")],
        body_chunks=[b""],
    )

    headers, body = http3_module._encode_response_headers(response)
    assert headers[0] == (b":status", b"204")
    assert (b"x-id", b"123") in headers
    assert (b"connection", b"close") not in headers
    assert (b"content-length", b"0") in headers
    assert body == b""


def test_create_http3_server_requires_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http3_module.importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing")),
    )

    async def request_handler(
        request: HTTPRequest,
        client: tuple[str, int],
        server: tuple[str, int],
    ) -> HTTPResponse:
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="h3",
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
    )

    with pytest.raises(RuntimeError, match="requires the 'aioquic' package"):
        asyncio.run(
            http3_module.create_http3_server(config=config, request_handler=request_handler)
        )


def test_create_http3_server_requires_cert_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    module_map = {
        "aioquic.asyncio": SimpleNamespace(serve=lambda *args, **kwargs: None),
        "aioquic.asyncio.protocol": SimpleNamespace(QuicConnectionProtocol=object),
        "aioquic.h3.connection": SimpleNamespace(H3_ALPN=["h3"], H3Connection=object),
        "aioquic.h3.events": SimpleNamespace(DataReceived=object, HeadersReceived=object),
        "aioquic.quic.configuration": SimpleNamespace(QuicConfiguration=object),
        "aioquic.quic.events": SimpleNamespace(ProtocolNegotiated=object),
    }
    monkeypatch.setattr(http3_module.importlib, "import_module", lambda name: module_map[name])

    async def request_handler(
        request: HTTPRequest,
        client: tuple[str, int],
        server: tuple[str, int],
    ) -> HTTPResponse:
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    cert_missing = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="h3",
        ssl_keyfile="key.pem",
    )
    with pytest.raises(RuntimeError, match="requires --ssl-certfile"):
        asyncio.run(
            http3_module.create_http3_server(config=cert_missing, request_handler=request_handler)
        )

    key_missing = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="h3",
        ssl_certfile="cert.pem",
    )
    with pytest.raises(RuntimeError, match="requires --ssl-keyfile"):
        asyncio.run(
            http3_module.create_http3_server(config=key_missing, request_handler=request_handler)
        )


def test_create_http3_server_dispatches_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProtocolNegotiated:
        def __init__(self, alpn_protocol: str) -> None:
            self.alpn_protocol = alpn_protocol

    class HeadersReceived:
        def __init__(
            self,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            stream_ended: bool,
        ) -> None:
            self.stream_id = stream_id
            self.headers = headers
            self.stream_ended = stream_ended

    class DataReceived:
        def __init__(self, stream_id: int, data: bytes, stream_ended: bool) -> None:
            self.stream_id = stream_id
            self.data = data
            self.stream_ended = stream_ended

    class QuicConfiguration:
        def __init__(self, is_client: bool, alpn_protocols: list[str]) -> None:
            self.is_client = is_client
            self.alpn_protocols = alpn_protocols
            self.cert_chain: tuple[str, str | None, str | None] | None = None

        def load_cert_chain(
            self,
            certfile: str,
            keyfile: str | None = None,
            password: str | None = None,
        ) -> None:
            self.cert_chain = (certfile, keyfile, password)

    class _FakeTransport:
        def get_extra_info(self, name: str) -> Any:
            if name == "peername":
                return ("127.0.0.1", 54321)
            if name == "sockname":
                return ("127.0.0.1", 8443)
            return None

    class QuicConnectionProtocol:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._quic = object()
            self._transport = _FakeTransport()
            self.transmit_calls = 0

        def transmit(self) -> None:
            self.transmit_calls += 1

        def connection_lost(self, exc: Exception | None) -> None:
            return None

    class H3Connection:
        instances: list[H3Connection] = []

        def __init__(self, quic: object) -> None:
            self.sent_headers: list[tuple[int, list[tuple[bytes, bytes]], bool]] = []
            self.sent_data: list[tuple[int, bytes, bool]] = []
            H3Connection.instances.append(self)

        def handle_event(self, event: object) -> list[object]:
            return list(getattr(event, "http_events", []))

        def send_headers(
            self,
            *,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool,
        ) -> None:
            self.sent_headers.append((stream_id, headers, end_stream))

        def send_data(self, *, stream_id: int, data: bytes, end_stream: bool) -> None:
            self.sent_data.append((stream_id, data, end_stream))

    observed_requests: list[HTTPRequest] = []
    captured: dict[str, Any] = {}
    server_object = SimpleNamespace(close=lambda: None, wait_closed=lambda: asyncio.sleep(0))

    async def serve(
        host: str,
        port: int,
        *,
        configuration: QuicConfiguration,
        create_protocol,
    ):
        captured["host"] = host
        captured["port"] = port
        captured["configuration"] = configuration

        protocol = create_protocol()
        protocol.quic_event_received(ProtocolNegotiated("h3"))
        protocol.quic_event_received(
            SimpleNamespace(
                http_events=[
                    HeadersReceived(
                        1,
                        [
                            (b":method", b"POST"),
                            (b":path", b"/upload?part=1"),
                            (b":authority", b"api.example.test"),
                            (b"x-a", b"1"),
                        ],
                        False,
                    )
                ]
            )
        )
        protocol.quic_event_received(SimpleNamespace(http_events=[DataReceived(1, b"body", True)]))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return server_object

    async def request_handler(
        request: HTTPRequest,
        client: tuple[str, int],
        server: tuple[str, int],
    ) -> HTTPResponse:
        observed_requests.append(request)
        assert client == ("127.0.0.1", 54321)
        assert server == ("127.0.0.1", 8443)
        return HTTPResponse(
            status=201,
            headers=[(b"x-server", b"palfrey")],
            body_chunks=[b"accepted"],
        )

    module_map = {
        "aioquic.asyncio": SimpleNamespace(serve=serve),
        "aioquic.asyncio.protocol": SimpleNamespace(QuicConnectionProtocol=QuicConnectionProtocol),
        "aioquic.h3.connection": SimpleNamespace(H3_ALPN=["h3"], H3Connection=H3Connection),
        "aioquic.h3.events": SimpleNamespace(
            DataReceived=DataReceived,
            HeadersReceived=HeadersReceived,
        ),
        "aioquic.quic.configuration": SimpleNamespace(QuicConfiguration=QuicConfiguration),
        "aioquic.quic.events": SimpleNamespace(ProtocolNegotiated=ProtocolNegotiated),
    }

    monkeypatch.setattr(http3_module.importlib, "import_module", lambda name: module_map[name])

    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="h3",
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
        ssl_keyfile_password="secret",
    )
    result = asyncio.run(
        http3_module.create_http3_server(config=config, request_handler=request_handler)
    )

    assert result is server_object
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["configuration"].cert_chain == ("cert.pem", "key.pem", "secret")

    assert observed_requests
    request = observed_requests[0]
    assert request.method == "POST"
    assert request.target == "/upload?part=1"
    assert request.body == b"body"

    h3_connection = H3Connection.instances[0]
    assert h3_connection.sent_headers
    assert h3_connection.sent_data
    assert any(
        (b":status", b"201") in header_block for _, header_block, _ in h3_connection.sent_headers
    )
