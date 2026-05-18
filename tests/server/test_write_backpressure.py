from __future__ import annotations

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPResponse
from palfrey.server import PalfreyServer


class DummyTransport:
    def __init__(self, high_watermark: int = 262_144):
        self.buffer_size = 0
        self.high_watermark = high_watermark
        self.drains = 0

    def get_write_buffer_limits(self):
        return self.high_watermark, self.high_watermark // 2

    def get_write_buffer_size(self):
        return self.buffer_size

    def set_write_buffer_limits(self, high=None, low=None):
        if high is not None:
            self.high_watermark = high


class DummyWriter:
    def __init__(self, transport: DummyTransport):
        self.transport = transport
        self.writes: list[bytes] = []

    def write(self, data: bytes):
        self.writes.append(data)
        self.transport.buffer_size += len(data)

    def writelines(self, data: list[bytes]):
        for chunk in data:
            self.write(chunk)

    async def drain(self):
        self.transport.drains += 1
        self.transport.buffer_size = 0


@pytest.mark.anyio
async def test_write_response_backpressure():
    config = PalfreyConfig(app="none")
    server = PalfreyServer(config)

    transport = DummyTransport(high_watermark=1000)
    writer = DummyWriter(transport)

    response = HTTPResponse(status=200, headers=[(b"content-length", b"3000")])
    response.body_chunks = [b"a" * 100] * 30
    await server._write_response(writer, response, keep_alive=True)  # type: ignore

    assert transport.drains > 1
    assert transport.buffer_size == 0
