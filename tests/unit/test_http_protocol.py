"""HTTP protocol helper tests."""

from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPResponse, append_default_response_headers, encode_http_response


def test_default_headers_are_added() -> None:
    response = HTTPResponse(status=200)
    response.body_chunks = [b"ok"]
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")

    append_default_response_headers(response, config)

    headers = {name.lower() for name, _ in response.headers}
    assert b"server" in headers
    assert b"date" in headers


def test_response_encoding_contains_status_line() -> None:
    response = HTTPResponse(status=200, headers=[(b"content-type", b"text/plain")])
    response.body_chunks = [b"hello"]

    raw = encode_http_response(response, keep_alive=False)
    assert raw.startswith(b"HTTP/1.1 200")
    assert b"hello" in raw
