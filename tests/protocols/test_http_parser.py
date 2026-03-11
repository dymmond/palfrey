from __future__ import annotations

import asyncio
from importlib.util import find_spec

import pytest

from palfrey.protocols.http import HTTPRequest, read_http_request, requires_100_continue
from tests.helpers import make_stream_reader


async def _read(
    payload: bytes,
    *,
    body_limit: int = 4_194_304,
    parser_mode: str = "auto",
) -> HTTPRequest | None:
    reader = await make_stream_reader(payload)
    return await read_http_request(reader, body_limit=body_limit, parser_mode=parser_mode)


def test_read_http_request_with_content_length_body() -> None:
    payload = b"POST /submit HTTP/1.1\r\nHost: test\r\nContent-Length: 5\r\n\r\nhello"
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.method == "POST"
    assert request.target == "/submit"
    assert request.body == b"hello"


def test_read_http_request_with_chunked_body() -> None:
    payload = (
        b"POST /chunked HTTP/1.1\r\n"
        b"Host: test\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"5\r\nhello\r\n"
        b"6\r\n world\r\n"
        b"0\r\n\r\n"
    )
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.body == b"hello world"


def test_read_http_request_returns_none_on_eof() -> None:
    assert asyncio.run(_read(b"")) is None


@pytest.mark.parametrize(
    "payload",
    [
        b"GET / HTTP/1.1\r\nHost: x\r\nContent-Length: nope\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\n",
    ],
)
def test_read_http_request_rejects_malformed_bodies(payload: bytes) -> None:
    with pytest.raises(ValueError):
        asyncio.run(_read(payload))


def test_read_http_request_rejects_large_content_length() -> None:
    payload = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 999\r\n\r\n"
    with pytest.raises(ValueError, match="HTTP body exceeds configured limit"):
        asyncio.run(_read(payload, body_limit=16))


def test_read_http_request_h11_parser_mode() -> None:
    payload = b"GET /hello HTTP/1.1\r\nHost: test\r\n\r\n"
    request = asyncio.run(_read(payload, parser_mode="h11"))
    assert request is not None
    assert request.method == "GET"
    assert request.target == "/hello"
    assert request.http_version == "HTTP/1.1"


@pytest.mark.skipif(find_spec("httptools") is None, reason="httptools is not installed")
def test_read_http_request_httptools_parser_mode() -> None:
    payload = b"GET /hello HTTP/1.1\r\nHost: test\r\n\r\n"
    request = asyncio.run(_read(payload, parser_mode="httptools"))
    assert request is not None
    assert request.method == "GET"
    assert request.target == "/hello"
    assert request.http_version == "HTTP/1.1"


@pytest.mark.skipif(find_spec("httptools") is None, reason="httptools is not installed")
def test_read_http_request_httptools_parser_mode_supports_upgrade_requests() -> None:
    payload = (
        b"GET / HTTP/1.1\r\n"
        b"Host: test\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Key: abcdefghijklmnop==\r\n"
        b"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    request = asyncio.run(_read(payload, parser_mode="httptools"))
    assert request is not None
    assert request.method == "GET"
    assert request.target == "/"
    assert request.http_version == "HTTP/1.1"
    headers = {(name.lower(), value.lower()) for name, value in request.headers}
    assert ("upgrade", "websocket") in headers
    assert ("connection", "upgrade") in headers


def test_requires_100_continue_detects_expect_header() -> None:
    request = HTTPRequest(
        method="POST",
        target="/",
        http_version="HTTP/1.1",
        headers=[("expect", "100-continue")],
        body=b"",
    )
    assert requires_100_continue(request) is True


def test_requires_100_continue_false_without_header() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )
    assert requires_100_continue(request) is False


# TDD Tests for Task 10: Single-Chunk Body Optimization
# Tests verify that Content-Length bodies arriving in one chunk return directly (no join)
# while multi-chunk bodies still join correctly.


def test_read_http_request_single_chunk_body_no_join() -> None:
    """Single-chunk POST body should return directly without b''.join()."""
    # 100 bytes of body that arrives in one TCP packet
    payload = b"POST /submit HTTP/1.1\r\nHost: test\r\nContent-Length: 100\r\n\r\n" + (b"x" * 100)
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.body == b"x" * 100
    # body_chunks should have exactly 1 chunk (the optimization target)
    assert len(request.body_chunks) == 1
    assert request.body_chunks[0] == b"x" * 100


def test_read_http_request_multi_chunk_body_joins_correctly() -> None:
    """Multi-chunk POST body should still join correctly via b''.join()."""
    # Large body (> 65536 bytes) that spans multiple 65536-byte read chunks
    large_payload = b"y" * 100_000
    payload = (
        b"POST /submit HTTP/1.1\r\nHost: test\r\nContent-Length: 100000\r\n\r\n" + large_payload
    )
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.body == large_payload
    # Multi-chunk body should be properly joined
    assert len(request.body_chunks) > 1
    assert b"".join(request.body_chunks) == large_payload


def test_read_http_request_empty_body_content_length_zero() -> None:
    """Content-Length: 0 should return b'' correctly."""
    payload = b"POST /empty HTTP/1.1\r\nHost: test\r\nContent-Length: 0\r\n\r\n"
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.body == b""
    # Empty body case should still work (returns [b""] from _read_content_length_body_chunks)
    assert len(request.body_chunks) >= 1
