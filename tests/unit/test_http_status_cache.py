"""Tests for pre-computed HTTP status lines and cached headers.

This module validates the performance optimization that pre-computes
common HTTP status lines (200, 201, 204, 301, 302, 400, 404, 500) as
module-level bytes constants and caches the Server header.

Key Test Scenarios:
- Common status codes use pre-computed bytes from _STATUS_LINES dict
- Uncommon status codes fall back to dynamic generation (e.g., 418, 451)
- Server header is cached as pre-encoded bytes
- Response encoding includes correct status lines and headers
"""

from __future__ import annotations

from palfrey.protocols.http import (
    HTTPResponse,
    encode_http_response,
    encode_http_response_chunks,
)


class TestStatusLineCache:
    """Tests for pre-computed status line caching."""

    def test_status_lines_dict_exists(self) -> None:
        """Pre-computed status lines dict is available at module level."""
        from palfrey.protocols import http

        assert hasattr(http, "_STATUS_LINES")
        assert isinstance(http._STATUS_LINES, dict)

    def test_common_status_codes_are_pre_computed(self) -> None:
        """Common status codes (200, 201, 204, 301, 302, 400, 404, 500) exist as bytes."""
        from palfrey.protocols import http

        common_codes = {200, 201, 204, 301, 302, 400, 404, 500}
        for code in common_codes:
            assert code in http._STATUS_LINES, f"Status {code} not in _STATUS_LINES"
            assert isinstance(http._STATUS_LINES[code], bytes), f"Status {code} not bytes"

    def test_status_line_format_200(self) -> None:
        """Status line for 200 has correct format: 'HTTP/1.1 200 OK\\r\\n'."""
        from palfrey.protocols import http

        assert http._STATUS_LINES[200] == b"HTTP/1.1 200 OK\r\n"

    def test_status_line_format_404(self) -> None:
        """Status line for 404 has correct format: 'HTTP/1.1 404 Not Found\\r\\n'."""
        from palfrey.protocols import http

        assert http._STATUS_LINES[404] == b"HTTP/1.1 404 Not Found\r\n"

    def test_status_line_format_500(self) -> None:
        """Status line for 500 has correct format: 'HTTP/1.1 500 Internal Server Error\\r\\n'."""
        from palfrey.protocols import http

        assert http._STATUS_LINES[500] == b"HTTP/1.1 500 Internal Server Error\r\n"

    def test_response_encoding_uses_pre_computed_status_line_200(self) -> None:
        """Encoding a 200 response uses the pre-computed status line."""
        response = HTTPResponse(status=200, headers=[(b"content-type", b"text/plain")])
        response.body_chunks = [b"OK"]

        raw = encode_http_response(response, keep_alive=False)

        # Should start with pre-computed status line
        assert raw.startswith(b"HTTP/1.1 200 OK\r\n")

    def test_response_encoding_uses_pre_computed_status_line_404(self) -> None:
        """Encoding a 404 response uses the pre-computed status line."""
        response = HTTPResponse(status=404, headers=[(b"content-type", b"text/plain")])
        response.body_chunks = [b"Not found"]

        raw = encode_http_response(response, keep_alive=False)

        # Should start with pre-computed status line
        assert raw.startswith(b"HTTP/1.1 404 Not Found\r\n")

    def test_uncommon_status_code_418_falls_back_to_dynamic_generation(self) -> None:
        """Uncommon status code (418) falls back to dynamic generation."""
        response = HTTPResponse(status=418, headers=[(b"content-type", b"text/plain")])
        response.body_chunks = [b"I'm a teapot"]

        raw = encode_http_response(response, keep_alive=False)

        # Should contain 418 status line dynamically generated
        assert b"HTTP/1.1 418" in raw
        assert b"I'm a teapot" in raw

    def test_uncommon_status_code_451_falls_back_to_dynamic_generation(self) -> None:
        """Uncommon status code (451) falls back to dynamic generation."""
        response = HTTPResponse(status=451)
        response.body_chunks = [b""]

        raw = encode_http_response(response, keep_alive=False)

        # Should contain 451 status line dynamically generated
        assert b"HTTP/1.1 451" in raw

    def test_custom_status_code_999_falls_back_gracefully(self) -> None:
        """Custom/invalid status code (999) falls back without crashing."""
        response = HTTPResponse(status=999, headers=[(b"content-type", b"text/plain")])
        response.body_chunks = [b"custom"]

        # Should not raise, just encode with empty reason phrase
        raw = encode_http_response(response, keep_alive=False)
        assert b"HTTP/1.1 999" in raw


class TestStatusLineChunking:
    """Tests for status line handling in chunked encoding path."""

    def test_encode_chunks_uses_pre_computed_status_line_200(self) -> None:
        """encode_http_response_chunks uses pre-computed status line for 200."""
        response = HTTPResponse(status=200)
        response.body_chunks = [b"Hello"]
        response.chunked_encoding = False

        chunks = list(encode_http_response_chunks(response, keep_alive=True))

        # First chunk should be the status line
        assert chunks[0] == b"HTTP/1.1 200 OK\r\n"

    def test_encode_chunks_uses_pre_computed_status_line_404(self) -> None:
        """encode_http_response_chunks uses pre-computed status line for 404."""
        response = HTTPResponse(status=404)
        response.body_chunks = [b"Not Found"]
        response.chunked_encoding = False

        chunks = list(encode_http_response_chunks(response, keep_alive=True))

        # First chunk should be the status line
        assert chunks[0] == b"HTTP/1.1 404 Not Found\r\n"

    def test_encode_chunks_uncommon_status_code_handled(self) -> None:
        """encode_http_response_chunks handles uncommon codes gracefully."""
        response = HTTPResponse(status=418)
        response.body_chunks = [b"teapot"]
        response.chunked_encoding = False

        chunks = list(encode_http_response_chunks(response, keep_alive=True))

        # First chunk should contain 418 status line
        first_chunk = chunks[0]
        assert b"HTTP/1.1 418" in first_chunk


class TestHeaderCaching:
    """Tests for Server and other header caching."""

    def test_response_includes_server_header_when_added(self) -> None:
        """Response encoding includes a Server header when explicitly added."""
        response = HTTPResponse(status=200, headers=[(b"server", b"palfrey")])
        response.body_chunks = [b"test"]

        raw = encode_http_response(response, keep_alive=False)

        assert b"server:" in raw.lower()

    def test_response_includes_date_header_when_added(self) -> None:
        """Response encoding includes a Date header when explicitly added."""
        response = HTTPResponse(status=200, headers=[(b"date", b"Mon, 01 Jan 2024 00:00:00 GMT")])
        response.body_chunks = [b"test"]

        raw = encode_http_response(response, keep_alive=False)

        assert b"date:" in raw.lower()

    def test_connection_header_included_for_keep_alive(self) -> None:
        """Connection header is included based on keep_alive flag."""
        response = HTTPResponse(status=200)
        response.body_chunks = [b"test"]

        raw_keep_alive = encode_http_response(response, keep_alive=True)
        raw_close = encode_http_response(response, keep_alive=False)

        # Check for connection header
        assert b"connection:" in raw_keep_alive.lower()
        assert b"connection:" in raw_close.lower()

        # keep_alive=True should have keep-alive
        assert b"keep-alive" in raw_keep_alive.lower()
        # keep_alive=False should have close
        assert b"close" in raw_close.lower()
