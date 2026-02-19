from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import (
    HTTPRequest,
    HTTPResponse,
    append_default_response_headers,
    encode_http_response,
    is_websocket_upgrade,
    should_keep_alive,
)


def test_default_headers_added_when_enabled() -> None:
    response = HTTPResponse(status=200, headers=[(b"content-type", b"text/plain")])
    response.body_chunks = [b"ok"]
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["x-extra: one"])

    append_default_response_headers(response, config)

    header_names = {name.lower() for name, _ in response.headers}
    assert b"server" in header_names
    assert b"date" in header_names
    assert b"x-extra" in header_names


def test_default_headers_not_added_when_disabled() -> None:
    response = HTTPResponse(status=200, headers=[])
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        server_header=False,
        date_header=False,
    )
    append_default_response_headers(response, config)
    header_names = {name.lower() for name, _ in response.headers}
    assert b"server" not in header_names
    assert b"date" not in header_names


def test_encode_http_response_adds_content_length() -> None:
    response = HTTPResponse(status=200, headers=[(b"content-type", b"text/plain")])
    response.body_chunks = [b"hello"]

    encoded = encode_http_response(response, keep_alive=False)
    assert b"content-length: 5" in encoded.lower()
    assert b"connection: close" in encoded.lower()


def test_encode_http_response_preserves_existing_content_length() -> None:
    response = HTTPResponse(status=200, headers=[(b"content-length", b"1")])
    response.body_chunks = [b"x"]

    encoded = encode_http_response(response, keep_alive=True)
    assert encoded.lower().count(b"content-length") == 1


def test_keep_alive_false_when_connection_close_in_request() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[("connection", "close")],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is False


def test_keep_alive_false_on_http10_without_keep_alive() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.0",
        headers=[],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is False


def test_keep_alive_true_for_http11_default() -> None:
    request = HTTPRequest(
        method="GET",
        target="/",
        http_version="HTTP/1.1",
        headers=[],
        body=b"",
    )
    response = HTTPResponse(status=200, headers=[])
    assert should_keep_alive(request, response) is True


def test_is_websocket_upgrade_detects_upgrade_headers() -> None:
    request = HTTPRequest(
        method="GET",
        target="/ws",
        http_version="HTTP/1.1",
        headers=[("upgrade", "websocket"), ("connection", "Upgrade")],
        body=b"",
    )
    assert is_websocket_upgrade(request)


def test_override_server_header_with_config_default() -> None:
    response = HTTPResponse(status=200, headers=[])
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        headers=[("Server", "over-ridden")],
    )
    append_default_response_headers(response, config)
    lowered = [(name.lower(), value) for name, value in response.headers]
    assert (b"server", b"over-ridden") in lowered
    assert (b"server", b"palfrey") not in lowered
    assert any(name == b"date" for name, _ in lowered)


def test_override_server_header_multiple_times() -> None:
    response = HTTPResponse(status=200, headers=[])
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        headers=[("Server", "one"), ("Server", "two")],
    )
    append_default_response_headers(response, config)
    server_values = [value for name, value in response.headers if name.lower() == b"server"]
    assert server_values == [b"one", b"two"]
