"""HTTP protocol parsing tests."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.protocols.http import HTTPRequest, read_http_request, requires_100_continue
from tests.helpers import make_stream_reader


def test_read_http_request_with_content_length_body() -> None:
    payload = b"POST /submit HTTP/1.1\r\nHost: test\r\nContent-Length: 5\r\n\r\nhello"
    request = asyncio.run(read_http_request(make_stream_reader(payload)))
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
    request = asyncio.run(read_http_request(make_stream_reader(payload)))
    assert request is not None
    assert request.body == b"hello world"


def test_read_http_request_returns_none_on_eof() -> None:
    assert asyncio.run(read_http_request(make_stream_reader(b""))) is None


@pytest.mark.parametrize(
    "payload",
    [
        b"GET / HTTP/1.1\r\nHost: x\r\nContent-Length: nope\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\n",
    ],
)
def test_read_http_request_rejects_malformed_bodies(payload: bytes) -> None:
    with pytest.raises(ValueError):
        asyncio.run(read_http_request(make_stream_reader(payload)))


def test_read_http_request_rejects_large_content_length() -> None:
    payload = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 999\r\n\r\n"
    with pytest.raises(ValueError, match="HTTP body exceeds configured limit"):
        asyncio.run(read_http_request(make_stream_reader(payload), body_limit=16))


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
