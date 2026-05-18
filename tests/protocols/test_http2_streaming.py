from __future__ import annotations

import asyncio

import palfrey.protocols.http2 as http2_module
from palfrey.protocols.http import HTTPResponse


class _Writer:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.drain_calls = 0

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        self.drain_calls += 1


def test_http2_large_response_streams_without_full_body_buffering() -> None:
    class Connection:
        def __init__(self) -> None:
            self.max_outbound_frame_size = 1_048_576
            self.headers_sent: list[tuple[int, list[tuple[bytes, bytes]], bool]] = []
            self.data_sent: list[tuple[int, bytes, bool]] = []

        def send_headers(
            self,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool,
        ) -> None:
            self.headers_sent.append((stream_id, headers, end_stream))

        def send_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
            self.data_sent.append((stream_id, data, end_stream))

        def data_to_send(self) -> bytes:
            return b""

    body_chunks = [b"a" * 262_144, b"b" * 262_144, b"c" * 262_144, b"d" * 262_144]
    response = HTTPResponse(
        status=200, headers=[(b"content-type", b"text/plain")], body_chunks=body_chunks
    )
    connection = Connection()
    writer = _Writer()

    asyncio.run(
        http2_module._send_h2_response(
            connection=connection,
            writer=writer,  # type: ignore[arg-type]
            stream_id=1,
            response=response,
        )
    )

    assert [chunk for _, chunk, _ in connection.data_sent] == body_chunks
    assert connection.data_sent[-1][2] is True


def test_http2_respects_flow_control_window_while_streaming() -> None:
    class FlowControlledConnection:
        def __init__(self) -> None:
            self.max_outbound_frame_size = 1_048_576
            self.window = 5
            self.data_sent: list[tuple[int, bytes, bool]] = []

        def local_flow_control_window(self, stream_id: int) -> int:
            return self.window

        def send_headers(
            self,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool,
        ) -> None:
            return None

        def send_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
            assert len(data) <= self.window
            self.window -= len(data)
            self.data_sent.append((stream_id, data, end_stream))

        def data_to_send(self) -> bytes:
            return b""

    class FlowWriter(_Writer):
        def __init__(self, connection: FlowControlledConnection) -> None:
            super().__init__()
            self._connection = connection

        async def drain(self) -> None:
            await super().drain()
            self._connection.window = 5

    response = HTTPResponse(status=200, headers=[], body_chunks=[b"abcdefghijkl"])
    connection = FlowControlledConnection()
    writer = FlowWriter(connection)

    asyncio.run(
        http2_module._send_h2_response(
            connection=connection,
            writer=writer,  # type: ignore[arg-type]
            stream_id=1,
            response=response,
        )
    )

    assert [len(chunk) for _, chunk, _ in connection.data_sent] == [5, 5, 2]
    assert connection.data_sent[-1][2] is True


def test_http2_streaming_handles_rst_stream_or_goaway_gracefully() -> None:
    class StreamClosedError(Exception):
        pass

    class ResettingConnection:
        def __init__(self) -> None:
            self.max_outbound_frame_size = 4
            self.calls = 0

        def send_headers(
            self,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool,
        ) -> None:
            return None

        def send_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
            self.calls += 1
            if self.calls >= 2:
                raise StreamClosedError("stream closed by peer")

        def data_to_send(self) -> bytes:
            return b""

    response = HTTPResponse(status=200, headers=[], body_chunks=[b"abcdef", b"ghijkl"])
    connection = ResettingConnection()
    writer = _Writer()

    asyncio.run(
        http2_module._send_h2_response(
            connection=connection,
            writer=writer,  # type: ignore[arg-type]
            stream_id=1,
            response=response,
        )
    )
