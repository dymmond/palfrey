"""Extended HTTP header behavior tests aligned with Uvicorn expectations."""

from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    append_default_response_headers,
    encode_http_response,
    should_keep_alive,
)


def _response_header_map(response: HTTPResponse) -> dict[bytes, list[bytes]]:
    mapped: dict[bytes, list[bytes]] = {}
    for name, value in response.headers:
        mapped.setdefault(name.lower(), []).append(value)
    return mapped


def test_default_headers_added_when_absent() -> None:
    response = HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])
    append_default_response_headers(response, PalfreyConfig(app="tests.fixtures.apps:http_app"))
    headers = _response_header_map(response)
    assert b"server" in headers
    assert b"date" in headers


def test_default_server_header_not_added_when_existing() -> None:
    response = HTTPResponse(status=200, headers=[(b"server", b"custom")], body_chunks=[b"ok"])
    append_default_response_headers(response, PalfreyConfig(app="tests.fixtures.apps:http_app"))
    headers = _response_header_map(response)
    assert headers[b"server"] == [b"custom"]


def test_default_date_header_not_added_when_existing() -> None:
    response = HTTPResponse(
        status=200, headers=[(b"date", b"Tue, 01 Jan 2030 00:00:00 GMT")], body_chunks=[b"ok"]
    )
    append_default_response_headers(response, PalfreyConfig(app="tests.fixtures.apps:http_app"))
    headers = _response_header_map(response)
    assert headers[b"date"] == [b"Tue, 01 Jan 2030 00:00:00 GMT"]


def test_configured_server_header_blocks_default_server_header() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["server: edge-proxy"])
    response = HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])
    append_default_response_headers(response, config)
    headers = _response_header_map(response)
    assert headers[b"server"] == [b"edge-proxy"]


def test_configured_date_header_blocks_default_date_header() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        headers=["date: Tue, 01 Jan 2030 00:00:00 GMT"],
    )
    response = HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])
    append_default_response_headers(response, config)
    headers = _response_header_map(response)
    assert headers[b"date"] == [b"Tue, 01 Jan 2030 00:00:00 GMT"]


def test_multiple_custom_headers_preserve_all_values() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app", headers=["x-a: one", "x-a: two", "x-b: three"]
    )
    response = HTTPResponse(status=200, headers=[], body_chunks=[b"ok"])
    append_default_response_headers(response, config)
    headers = _response_header_map(response)
    assert headers[b"x-a"] == [b"one", b"two"]
    assert headers[b"x-b"] == [b"three"]


def test_encode_http_response_uses_default_reason_for_unknown_status() -> None:
    payload = encode_http_response(
        HTTPResponse(status=299, headers=[], body_chunks=[b"ok"]), keep_alive=True
    )
    assert payload.startswith(b"HTTP/1.1 299 ")


def test_encode_http_response_emits_keep_alive_header_when_enabled() -> None:
    payload = encode_http_response(
        HTTPResponse(status=200, headers=[], body_chunks=[b"ok"]), keep_alive=True
    )
    assert b"connection: keep-alive" in payload.lower()


def test_encode_http_response_does_not_duplicate_content_length_header() -> None:
    payload = encode_http_response(
        HTTPResponse(status=200, headers=[(b"content-length", b"2")], body_chunks=[b"ok"]),
        keep_alive=True,
    )
    assert payload.lower().count(b"content-length") == 1


def test_should_keep_alive_false_when_response_connection_close_is_mixed_case() -> None:
    request = HTTPRequest(method="GET", target="/", http_version="HTTP/1.1", headers=[], body=b"")
    response = HTTPResponse(status=200, headers=[(b"Connection", b"Close")])
    assert should_keep_alive(request, response) is False


def test_should_keep_alive_true_for_http10_with_explicit_keep_alive() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.0",
        headers=[("Connection", "keep-alive")],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is True
