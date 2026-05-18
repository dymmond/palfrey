from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import patch

import palfrey.server as server_module
from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPResponse
from palfrey.server import PalfreyServer


class _FakeTransport:
    def __init__(self, writer: _BaseWriter) -> None:
        self._writer = writer
        self.size_checks = 0

    def get_write_buffer_size(self) -> int:
        self.size_checks += 1
        return self._writer.buffer_size


class _BaseWriter:
    def __init__(self) -> None:
        self.buffer_size = 0
        self.drain_calls = 0
        self.events: list[str] = []
        self.transport = _FakeTransport(self)

    async def drain(self) -> None:
        self.events.append("drain")
        self.drain_calls += 1
        self.buffer_size = 0


class _WriterNoWritelines(_BaseWriter):
    def write(self, data: bytes) -> None:
        self.events.append("write")
        self.buffer_size += len(data)


class _WriterWithWritelines(_BaseWriter):
    def __init__(self) -> None:
        super().__init__()
        self.writelines_calls = 0

    def write(self, data: bytes) -> None:
        self.events.append("write")
        self.buffer_size += len(data)

    def writelines(self, data) -> None:
        self.events.append("writelines")
        self.writelines_calls += 1
        for chunk in data:
            self.buffer_size += len(chunk)


def test_write_response_drains_when_buffer_exceeds_high_watermark() -> None:
    async def scenario() -> None:
        server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
        writer = _WriterNoWritelines()

        with patch.object(
            server_module,
            "encode_http_response_chunks",
            lambda _response, keep_alive: [b"x" * 300_000, b"tail"],
        ):
            await server._write_response(
                cast("asyncio.StreamWriter", writer),
                HTTPResponse(status=200, headers=[]),
                keep_alive=True,
            )

        assert writer.drain_calls >= 2
        assert writer.transport.size_checks >= 1

    asyncio.run(scenario())


def test_write_response_resumes_writing_after_drain() -> None:
    async def scenario() -> None:
        server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
        writer = _WriterNoWritelines()

        with patch.object(
            server_module,
            "encode_http_response_chunks",
            lambda _response, keep_alive: [b"x" * 300_000, b"y" * 64],
        ):
            await server._write_response(
                cast("asyncio.StreamWriter", writer),
                HTTPResponse(status=200, headers=[]),
                keep_alive=True,
            )

        assert writer.events.index("drain") < len(writer.events) - 1
        assert writer.events[-1] == "drain"
        assert writer.events[-2] == "write"

    asyncio.run(scenario())


def test_write_response_non_congested_path_avoids_backpressure_checks() -> None:
    async def scenario() -> None:
        server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
        writer = _WriterNoWritelines()

        with patch.object(
            server_module,
            "encode_http_response_chunks",
            lambda _response, keep_alive: [b"ok", b"done"],
        ):
            await server._write_response(
                cast("asyncio.StreamWriter", writer),
                HTTPResponse(status=200, headers=[]),
                keep_alive=True,
            )

        assert writer.transport.size_checks == 0
        assert writer.drain_calls == 1

    asyncio.run(scenario())


def test_chunked_streaming_with_writelines_respects_backpressure() -> None:
    async def scenario() -> None:
        server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
        writer = _WriterWithWritelines()

        with patch.object(
            server_module,
            "encode_http_response_chunks",
            lambda _response, keep_alive: [b"a" * 180_000, b"b" * 180_000, b"tail"],
        ):
            response = HTTPResponse(
                status=200,
                headers=[(b"transfer-encoding", b"chunked")],
                body_chunks=[b"abc", b"def"],
                chunked_encoding=True,
            )
            await server._write_response(
                cast("asyncio.StreamWriter", writer), response, keep_alive=True
            )

        assert writer.writelines_calls >= 2
        assert writer.drain_calls >= 2
        assert writer.transport.size_checks >= 1

    asyncio.run(scenario())
