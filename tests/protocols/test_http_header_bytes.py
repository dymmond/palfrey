from __future__ import annotations

import asyncio
from importlib.util import find_spec

from palfrey.protocols.http import HTTPRequest, build_http_scope, read_http_request
from tests.helpers import make_stream_reader


async def _read(payload: bytes, *, parser_mode: str) -> HTTPRequest | None:
    reader = await make_stream_reader(payload)
    return await read_http_request(reader, parser_mode=parser_mode)


def test_httptools_headers_stay_bytes_through_scope_pipeline() -> None:
    if find_spec("httptools") is None:
        return
    payload = (
        b"GET /hello?x=1 HTTP/1.1\r\n"
        b"Host: Example.test\r\n"
        b"X-Custom: TestValue\r\n"
        b"X-Binary: caf\xe9\r\n\r\n"
    )

    request = asyncio.run(_read(payload, parser_mode="httptools"))
    assert request is not None

    scope = build_http_scope(
        request,
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        root_path="",
        is_tls=False,
    )

    assert all(
        isinstance(name, bytes) and isinstance(value, bytes) for name, value in request.headers
    )
    assert all(
        isinstance(name, bytes) and isinstance(value, bytes) for name, value in scope["headers"]
    )
    assert (b"x-custom", b"TestValue") in scope["headers"]
    assert (b"x-binary", b"caf\xe9") in scope["headers"]


def test_h11_headers_stay_bytes_through_scope_pipeline() -> None:
    payload = (
        b"GET /hello?x=1 HTTP/1.1\r\n"
        b"Host: Example.test\r\n"
        b"X-Custom: TestValue\r\n"
        b"X-Binary: caf\xe9\r\n\r\n"
    )

    request = asyncio.run(_read(payload, parser_mode="h11"))
    assert request is not None

    scope = build_http_scope(
        request,
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        root_path="",
        is_tls=False,
    )

    assert all(
        isinstance(name, bytes) and isinstance(value, bytes) for name, value in request.headers
    )
    assert all(
        isinstance(name, bytes) and isinstance(value, bytes) for name, value in scope["headers"]
    )
    assert (b"x-custom", b"TestValue") in scope["headers"]
    assert (b"x-binary", b"caf\xe9") in scope["headers"]


def test_build_http_scope_keeps_header_tuple_identity_for_lowercase_bytes() -> None:
    host = (b"host", b"example.test")
    custom = (b"x-token", b"abc")
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[host, custom],
        body=b"",
    )

    scope = build_http_scope(
        request,
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        root_path="",
        is_tls=False,
    )

    assert scope["headers"] is request.headers
    assert scope["headers"][0] is host
    assert scope["headers"][1] is custom


def test_httptools_header_names_are_lowercased_as_bytes() -> None:
    if find_spec("httptools") is None:
        return
    payload = b"GET / HTTP/1.1\r\nX-CuStOm: value\r\n\r\n"

    request = asyncio.run(_read(payload, parser_mode="httptools"))
    assert request is not None

    header_name, header_value = request.headers[0]
    assert header_name == b"x-custom"
    assert header_value == b"value"
    assert isinstance(header_name, bytes)
    assert isinstance(header_value, bytes)
