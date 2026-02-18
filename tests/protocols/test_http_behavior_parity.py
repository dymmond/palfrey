"""HTTP behavior parity tests adapted from Uvicorn HTTP expectations."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    append_default_response_headers,
    encode_http_response,
    is_websocket_upgrade,
    read_http_request,
    requires_100_continue,
    should_keep_alive,
)
from tests.helpers import make_stream_reader


async def _read(payload: bytes, *, max_head_size: int = 1_048_576) -> HTTPRequest | None:
    reader = await make_stream_reader(payload)
    return await read_http_request(reader, max_head_size=max_head_size)


def test_is_websocket_upgrade_true_for_upgrade_and_connection_headers() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[("Connection", "upgrade"), ("Upgrade", "websocket")],
        body=b"",
    )
    assert is_websocket_upgrade(request) is True


def test_is_websocket_upgrade_false_when_upgrade_value_not_websocket() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[("Connection", "upgrade"), ("Upgrade", "h2c")],
        body=b"",
    )
    assert is_websocket_upgrade(request) is False


def test_requires_100_continue_is_case_insensitive() -> None:
    request = HTTPRequest(
        method="POST",
        target="/",
        http_version="HTTP/1.1",
        headers=[("Expect", "100-CONTINUE")],
        body=b"",
    )
    assert requires_100_continue(request) is True


def test_requires_100_continue_false_for_unrelated_expectation() -> None:
    request = HTTPRequest(
        method="POST",
        target="/",
        http_version="HTTP/1.1",
        headers=[("Expect", "something-else")],
        body=b"",
    )
    assert requires_100_continue(request) is False


def test_should_keep_alive_false_for_http10_without_keep_alive_header() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.0",
        headers=[],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is False


def test_should_keep_alive_false_when_request_has_connection_close() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[("Connection", "close")],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is False


def test_should_keep_alive_true_for_http11_without_connection_close() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is True


def test_encode_http_response_injects_content_length_when_missing() -> None:
    response = HTTPResponse(
        status=200, headers=[(b"content-type", b"text/plain")], body_chunks=[b"hello"]
    )
    payload = encode_http_response(response, keep_alive=True)
    assert b"content-length: 5" in payload.lower()


def test_encode_http_response_keeps_user_content_length_when_present() -> None:
    response = HTTPResponse(
        status=200,
        headers=[(b"content-length", b"999"), (b"content-type", b"text/plain")],
        body_chunks=[b"hello"],
    )
    payload = encode_http_response(response, keep_alive=True)
    assert b"content-length: 999" in payload.lower()
    assert b"content-length: 5" not in payload.lower()


def test_encode_http_response_sets_connection_close_header() -> None:
    response = HTTPResponse(status=200, headers=[], body_chunks=[b""])
    payload = encode_http_response(response, keep_alive=False)
    assert b"connection: close" in payload.lower()


def test_append_default_response_headers_adds_server_and_date_by_default() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    response = HTTPResponse(status=200, headers=[])
    append_default_response_headers(response, config)
    names = {name.lower() for name, _ in response.headers}
    assert b"server" in names
    assert b"date" in names


def test_append_default_response_headers_respects_server_header_toggle() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", server_header=False)
    response = HTTPResponse(status=200, headers=[])
    append_default_response_headers(response, config)
    names = {name.lower() for name, _ in response.headers}
    assert b"server" not in names


def test_append_default_response_headers_respects_date_header_toggle() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", date_header=False)
    response = HTTPResponse(status=200, headers=[])
    append_default_response_headers(response, config)
    names = {name.lower() for name, _ in response.headers}
    assert b"date" not in names


def test_append_default_response_headers_appends_custom_headers() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["x-test: one"])
    response = HTTPResponse(status=200, headers=[])
    append_default_response_headers(response, config)
    assert (b"x-test", b"one") in response.headers


def test_read_http_request_rejects_head_over_limit() -> None:
    payload = b"GET / HTTP/1.1\r\nHost: example.org\r\n\r\n"
    with pytest.raises(ValueError, match="HTTP head exceeds configured limit"):
        asyncio.run(_read(payload, max_head_size=8))


def test_read_http_request_rejects_invalid_chunk_size() -> None:
    payload = b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\nhello\r\n"
    with pytest.raises(ValueError, match="Malformed chunked encoding size"):
        asyncio.run(_read(payload))


def test_read_http_request_parses_http10_request() -> None:
    payload = b"GET / HTTP/1.0\r\nHost: x\r\n\r\n"
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.http_version == "HTTP/1.0"


def test_read_http_request_accepts_request_without_body() -> None:
    payload = b"GET / HTTP/1.1\r\nHost: x\r\n\r\n"
    request = asyncio.run(_read(payload))
    assert request is not None
    assert request.body == b""
