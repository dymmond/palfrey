"""Additional HTTP protocol behavior tests."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    build_http_scope,
    read_http_request,
    run_http_asgi,
    should_keep_alive,
)
from tests.helpers import make_stream_reader


def test_build_http_scope_populates_asgi_fields() -> None:
    request = HTTPRequest(
        method="GET",
        target="/a%20path/resource?x=1&y=2",
        http_version="HTTP/1.1",
        headers=[("host", "example.test"), ("x-token", "abc")],
        body=b"",
    )

    scope = build_http_scope(
        request,
        client=("10.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        root_path="/api",
        is_tls=True,
    )

    assert scope["type"] == "http"
    assert scope["http_version"] == "1.1"
    assert scope["scheme"] == "https"
    assert scope["path"] == "/api/a path/resource"
    assert scope["raw_path"] == b"/api/a%20path/resource"
    assert scope["query_string"] == b"x=1&y=2"
    assert scope["headers"] == [(b"host", b"example.test"), (b"x-token", b"abc")]


def test_run_http_asgi_collects_response_body_chunks() -> None:
    async def app(scope, receive, send):
        message = await receive()
        assert message["type"] == "http.request"
        assert message["body"] == b"payload"

        await send({"type": "http.response.start", "status": 201, "headers": [(b"x", b"1")]})
        await send({"type": "http.response.body", "body": b"hello ", "more_body": True})
        await send({"type": "http.response.body", "body": b"world", "more_body": False})
        await send({"type": "http.response.body", "body": b"ignored", "more_body": False})

    response = asyncio.run(
        run_http_asgi(
            app,
            {"type": "http", "headers": [], "path": "/", "method": "GET", "state": {}},
            b"payload",
        )
    )

    assert response.status == 201
    assert response.headers == [(b"x", b"1")]
    assert response.body_chunks == [b"hello ", b"world"]


def test_run_http_asgi_rejects_unknown_message_types() -> None:
    async def app(scope, receive, send):
        await send({"type": "http.response.wat"})

    with pytest.raises(RuntimeError, match="Unsupported HTTP ASGI message type"):
        asyncio.run(
            run_http_asgi(
                app,
                {"type": "http", "headers": [], "path": "/", "method": "GET", "state": {}},
                b"",
            )
        )


def test_should_keep_alive_false_when_response_requests_close() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[(b"connection", b"close")])
    assert should_keep_alive(request, response) is False


def test_should_keep_alive_true_for_http10_keep_alive_header() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.0",
        headers=[("connection", "keep-alive")],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is True


def test_read_http_request_rejects_malformed_chunk_delimiter() -> None:
    payload = b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhelloXX"

    async def scenario() -> None:
        reader = await make_stream_reader(payload)
        await read_http_request(reader)

    with pytest.raises(ValueError, match="Malformed chunk delimiter"):
        asyncio.run(scenario())


def test_read_http_request_rejects_chunked_eof() -> None:
    payload = b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n"

    async def scenario() -> None:
        reader = await make_stream_reader(payload)
        await read_http_request(reader)

    with pytest.raises(ValueError, match="Unexpected EOF while reading chunked body"):
        asyncio.run(scenario())


def test_read_http_request_rejects_chunked_body_over_limit() -> None:
    payload = (
        b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n"
        b"5\r\nhello\r\n"
        b"5\r\nworld\r\n"
        b"0\r\n\r\n"
    )

    async def scenario() -> None:
        reader = await make_stream_reader(payload)
        await read_http_request(reader, body_limit=8)

    with pytest.raises(ValueError, match="HTTP body exceeds configured limit"):
        asyncio.run(scenario())
