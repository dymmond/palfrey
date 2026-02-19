from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import palfrey.protocols.http2 as http2_module
from palfrey.protocols.http import HTTPRequest, HTTPResponse
from tests.helpers import make_stream_reader


class _Writer:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed


def test_decode_request_headers_adds_host_from_authority() -> None:
    method, target, headers = http2_module._decode_request_headers(
        [
            (b":method", b"POST"),
            (b":path", b"/items?limit=1"),
            (b":authority", b"api.example.com"),
            (b"x-trace", b"abc"),
        ]
    )
    assert method == "POST"
    assert target == "/items?limit=1"
    assert ("x-trace", "abc") in headers
    assert ("host", "api.example.com") in headers


def test_encode_response_headers_filters_connection_specific_values() -> None:
    response = HTTPResponse(
        status=201,
        headers=[
            (b"connection", b"close"),
            (b"transfer-encoding", b"chunked"),
            (b"x-result", b"ok"),
        ],
        body_chunks=[b"payload"],
    )

    headers, body = http2_module._encode_response_headers(response)
    assert headers[0] == (b":status", b"201")
    assert (b"x-result", b"ok") in headers
    assert (b"connection", b"close") not in headers
    assert (b"transfer-encoding", b"chunked") not in headers
    assert (b"content-length", b"7") in headers
    assert body == b"payload"


def test_serve_http2_connection_requires_h2_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http2_module.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError(name)),
    )
    reader = asyncio.run(make_stream_reader(b""))
    writer = _Writer()

    async def handler(_request: HTTPRequest) -> HTTPResponse:
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    with pytest.raises(RuntimeError, match="requires the 'h2' package"):
        asyncio.run(
            http2_module.serve_http2_connection(
                reader=reader,
                writer=writer,  # type: ignore[arg-type]
                request_handler=handler,
            )
        )


def test_serve_http2_connection_processes_request_and_sends_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RequestReceived:
        def __init__(self, stream_id: int, headers, stream_ended: bool = False) -> None:
            self.stream_id = stream_id
            self.headers = headers
            self.stream_ended = stream_ended

    class DataReceived:
        def __init__(
            self,
            stream_id: int,
            data: bytes,
            flow_controlled_length: int,
            stream_ended: bool,
        ) -> None:
            self.stream_id = stream_id
            self.data = data
            self.flow_controlled_length = flow_controlled_length
            self.stream_ended = stream_ended

    class StreamEnded:
        def __init__(self, stream_id: int) -> None:
            self.stream_id = stream_id

    class StreamReset:
        def __init__(self, stream_id: int) -> None:
            self.stream_id = stream_id

    class H2Error(Exception):
        pass

    class H2Configuration:
        def __init__(self, client_side: bool, header_encoding) -> None:
            self.client_side = client_side
            self.header_encoding = header_encoding

    class H2Connection:
        instances: list[H2Connection] = []

        def __init__(self, config: H2Configuration) -> None:
            self.config = config
            self._outbound: list[bytes] = []
            self.headers_sent: list[tuple[int, list[tuple[bytes, bytes]], bool]] = []
            self.data_sent: list[tuple[int, bytes, bool]] = []
            self.acks: list[tuple[int, int]] = []
            H2Connection.instances.append(self)

        def initiate_connection(self) -> None:
            self._outbound.append(b"server-preface")

        def data_to_send(self) -> bytes:
            if self._outbound:
                return self._outbound.pop(0)
            return b""

        def receive_data(self, data: bytes):
            if data == b"request":
                return [
                    RequestReceived(
                        1,
                        [
                            (b":method", b"POST"),
                            (b":path", b"/submit?item=1"),
                            (b":authority", b"example.test"),
                            (b"x-a", b"1"),
                        ],
                    ),
                    DataReceived(1, b"hello", 5, True),
                ]
            if data == b"bad":
                raise H2Error("boom")
            return []

        def send_headers(
            self,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool,
        ) -> None:
            self.headers_sent.append((stream_id, headers, end_stream))
            self._outbound.append(b"headers")

        def send_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
            self.data_sent.append((stream_id, data, end_stream))
            self._outbound.append(b"data")

        def acknowledge_received_data(self, flow_controlled_length: int, stream_id: int) -> None:
            self.acks.append((flow_controlled_length, stream_id))

        def close_connection(self) -> None:
            self._outbound.append(b"close")

    module_map = {
        "h2.config": SimpleNamespace(H2Configuration=H2Configuration),
        "h2.connection": SimpleNamespace(H2Connection=H2Connection),
        "h2.events": SimpleNamespace(
            DataReceived=DataReceived,
            RequestReceived=RequestReceived,
            StreamEnded=StreamEnded,
            StreamReset=StreamReset,
        ),
        "h2.exceptions": SimpleNamespace(H2Error=H2Error),
    }

    monkeypatch.setattr(
        http2_module.importlib,
        "import_module",
        lambda name: module_map[name],
    )

    observed_requests: list[HTTPRequest] = []

    async def request_handler(request: HTTPRequest) -> HTTPResponse:
        observed_requests.append(request)
        return HTTPResponse(
            status=202,
            headers=[(b"x-powered-by", b"palfrey")],
            body_chunks=[b"accepted"],
        )

    reader = asyncio.run(make_stream_reader(b"request"))
    writer = _Writer()
    asyncio.run(
        http2_module.serve_http2_connection(
            reader=reader,
            writer=writer,  # type: ignore[arg-type]
            request_handler=request_handler,
        )
    )

    assert observed_requests
    parsed_request = observed_requests[0]
    assert parsed_request.method == "POST"
    assert parsed_request.target == "/submit?item=1"
    assert parsed_request.body == b"hello"
    assert ("host", "example.test") in parsed_request.headers

    connection = H2Connection.instances[0]
    assert connection.acks == [(5, 1)]
    assert connection.headers_sent
    assert connection.data_sent
    assert any(
        (b":status", b"202") in header_block for _, header_block, _ in connection.headers_sent
    )
    assert writer.writes


def test_serve_http2_connection_closes_on_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RequestReceived:
        def __init__(self, stream_id: int, headers, stream_ended: bool = False) -> None:
            self.stream_id = stream_id
            self.headers = headers
            self.stream_ended = stream_ended

    class DataReceived:
        def __init__(
            self, stream_id: int, data: bytes, flow_controlled_length: int, stream_ended: bool
        ) -> None:
            self.stream_id = stream_id
            self.data = data
            self.flow_controlled_length = flow_controlled_length
            self.stream_ended = stream_ended

    class StreamEnded:
        def __init__(self, stream_id: int) -> None:
            self.stream_id = stream_id

    class StreamReset:
        def __init__(self, stream_id: int) -> None:
            self.stream_id = stream_id

    class H2Error(Exception):
        pass

    class H2Configuration:
        def __init__(self, client_side: bool, header_encoding) -> None:
            self.client_side = client_side
            self.header_encoding = header_encoding

    class H2Connection:
        def __init__(self, config: H2Configuration) -> None:
            self._outbound: list[bytes] = []

        def initiate_connection(self) -> None:
            self._outbound.append(b"preface")

        def data_to_send(self) -> bytes:
            if self._outbound:
                return self._outbound.pop(0)
            return b""

        def receive_data(self, _data: bytes):
            raise H2Error("invalid frame")

        def send_headers(
            self, stream_id: int, headers: list[tuple[bytes, bytes]], end_stream: bool
        ) -> None:
            return None

        def send_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
            return None

        def acknowledge_received_data(self, flow_controlled_length: int, stream_id: int) -> None:
            return None

        def close_connection(self) -> None:
            self._outbound.append(b"goaway")

    module_map = {
        "h2.config": SimpleNamespace(H2Configuration=H2Configuration),
        "h2.connection": SimpleNamespace(H2Connection=H2Connection),
        "h2.events": SimpleNamespace(
            DataReceived=DataReceived,
            RequestReceived=RequestReceived,
            StreamEnded=StreamEnded,
            StreamReset=StreamReset,
        ),
        "h2.exceptions": SimpleNamespace(H2Error=H2Error),
    }

    monkeypatch.setattr(
        http2_module.importlib,
        "import_module",
        lambda name: module_map[name],
    )

    async def request_handler(_request: HTTPRequest) -> HTTPResponse:
        return HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])

    reader = asyncio.run(make_stream_reader(b"bad"))
    writer = _Writer()
    asyncio.run(
        http2_module.serve_http2_connection(
            reader=reader,
            writer=writer,  # type: ignore[arg-type]
            request_handler=request_handler,
        )
    )

    assert writer.writes[-1] == b"goaway"
