"""HTTP/1.1 protocol handling for Palfrey."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from palfrey.acceleration import parse_request_head
from palfrey.config import PalfreyConfig
from palfrey.http_date import cached_http_date_header
from palfrey.types import ASGIApplication, ClientAddress, Headers, Message, Scope, ServerAddress


@dataclass(slots=True)
class HTTPRequest:
    """Parsed HTTP request metadata and body payload."""

    method: str
    target: str
    http_version: str
    headers: list[tuple[str, str]]
    body: bytes


@dataclass(slots=True)
class HTTPResponse:
    """HTTP response assembled from ASGI send events."""

    status: int = 500
    headers: Headers = field(default_factory=list)
    body_chunks: list[bytes] = field(default_factory=list)


class _HTTPToolsParserProtocol:
    """Fast callback protocol for ``httptools.HttpRequestParser``."""

    __slots__ = ("method", "target", "http_version", "headers", "_parser")

    def __init__(self) -> None:
        """Initialize parser callback state."""

        self.method = ""
        self.target = ""
        self.http_version = "HTTP/1.1"
        self.headers: list[tuple[str, str]] = []
        self._parser: Any = None

    def bind_parser(self, parser: Any) -> None:
        """Attach parser object for method/version extraction callbacks."""

        self._parser = parser

    def on_url(self, url: bytes) -> None:
        """Capture request URL bytes."""

        self.target = url.decode("latin-1")

    def on_header(self, name: bytes, value: bytes) -> None:
        """Capture header tuple bytes as decoded latin-1 strings."""

        self.headers.append((name.decode("latin-1"), value.decode("latin-1")))

    def on_headers_complete(self) -> None:
        """Capture parsed method and protocol version."""

        parser = self._parser
        self.http_version = f"HTTP/{parser.get_http_version()}"
        self.method = parser.get_method().decode("latin-1")

    def on_message_complete(self) -> None:
        """Complete request head callback."""

        return None


_HTTPTOOLS_MODULE: Any | None = None
_HTTPTOOLS_UPGRADE_EXC_TYPE: type[BaseException] | None = None


def _get_httptools_backend() -> tuple[Any, type[BaseException] | None]:
    """Load and cache ``httptools`` module and upgrade exception type."""

    global _HTTPTOOLS_MODULE, _HTTPTOOLS_UPGRADE_EXC_TYPE

    if _HTTPTOOLS_MODULE is not None:
        return _HTTPTOOLS_MODULE, _HTTPTOOLS_UPGRADE_EXC_TYPE

    try:
        import httptools
    except ImportError as exc:  # pragma: no cover - dependency validation in config.
        raise ValueError("httptools parser is unavailable") from exc

    upgrade_exc = getattr(getattr(httptools, "parser", None), "errors", None)
    upgrade_exc_type = getattr(upgrade_exc, "HttpParserUpgrade", None)
    if not isinstance(upgrade_exc_type, type):
        upgrade_exc_type = None

    _HTTPTOOLS_MODULE = httptools
    _HTTPTOOLS_UPGRADE_EXC_TYPE = upgrade_exc_type
    return httptools, upgrade_exc_type


def _http_date_header() -> bytes:
    return cached_http_date_header()


def _normalize_connection_value(headers: list[tuple[str, str]]) -> str:
    for name, value in headers:
        if name.lower() == "connection":
            return value.lower()
    return ""


def _is_websocket_upgrade(headers: list[tuple[str, str]]) -> bool:
    upgrade = ""
    connection = ""
    for name, value in headers:
        lowered_name = name.lower()
        lowered_value = value.lower()
        if lowered_name == "upgrade":
            upgrade = lowered_value
        elif lowered_name == "connection":
            connection = lowered_value
    return "websocket" in upgrade and "upgrade" in connection


def _header_lookup(headers: list[tuple[str, str]], key: str) -> str | None:
    for name, value in headers:
        if name.lower() == key.lower():
            return value
    return None


async def _read_chunked_body(reader: asyncio.StreamReader, body_limit: int) -> bytes:
    body_chunks: list[bytes] = []
    total = 0

    while True:
        chunk_size_line = await reader.readline()
        if not chunk_size_line:
            raise ValueError("Unexpected EOF while reading chunked body")

        chunk_size_text = chunk_size_line.split(b";", 1)[0].strip()
        try:
            chunk_size = int(chunk_size_text, 16)
        except ValueError as exc:
            raise ValueError("Malformed chunked encoding size") from exc

        if chunk_size == 0:
            await reader.readuntil(b"\r\n")
            break

        chunk = await reader.readexactly(chunk_size)
        body_chunks.append(chunk)
        total += len(chunk)
        if total > body_limit:
            raise ValueError("HTTP body exceeds configured limit")

        line_end = await reader.readexactly(2)
        if line_end != b"\r\n":
            raise ValueError("Malformed chunk delimiter")

    return b"".join(body_chunks)


async def read_http_request(
    reader: asyncio.StreamReader,
    *,
    max_head_size: int = 1_048_576,
    body_limit: int = 4_194_304,
    parser_mode: str = "auto",
) -> HTTPRequest | None:
    """Read and parse one HTTP request from a stream.

    Args:
        reader: Client stream reader.
        max_head_size: Maximum allowed head bytes before delimiter.
        body_limit: Maximum body bytes accepted for a single request.

    Returns:
        Parsed request object, or ``None`` when EOF is reached.

    Raises:
        ValueError: If parsing fails or limits are exceeded.
    """

    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as exc:
        raise ValueError("HTTP head exceeds configured limit") from exc
    except asyncio.IncompleteReadError:
        return None

    if len(head) > max_head_size:
        raise ValueError("HTTP head exceeds configured limit")

    method, target, version, headers = _parse_request_head(head, parser_mode)

    content_length_raw = _header_lookup(headers, "content-length")
    transfer_encoding = (_header_lookup(headers, "transfer-encoding") or "").lower()

    content_length = 0
    if content_length_raw is not None:
        try:
            content_length = int(content_length_raw)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header") from exc

    if content_length > body_limit:
        raise ValueError("HTTP body exceeds configured limit")

    body = b""
    if "chunked" in transfer_encoding:
        body = await _read_chunked_body(reader, body_limit)
    elif content_length > 0:
        body = await reader.readexactly(content_length)

    return HTTPRequest(
        method=method,
        target=target,
        http_version=version,
        headers=headers,
        body=body,
    )


def _parse_request_head(
    head: bytes,
    parser_mode: str,
) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Parse request head bytes with configured backend mode.

    Args:
        head: Raw request head bytes ending with CRLFCRLF.
        parser_mode: HTTP parser mode.

    Returns:
        Parsed request line and headers.

    Raises:
        ValueError: If the parser mode cannot decode request bytes.
    """

    if parser_mode == "h11":
        return _parse_request_head_h11(head)
    if parser_mode == "httptools":
        return _parse_request_head_httptools(head)

    try:
        return parse_request_head(head)
    except ValueError:
        with suppress(ValueError):
            return _parse_request_head_httptools(head)
        return _parse_request_head_h11(head)


def _parse_request_head_h11(
    head: bytes,
) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Parse HTTP request head using ``h11`` for parity mode."""

    try:
        import h11
    except ImportError as exc:  # pragma: no cover - dependency validation in config.
        raise ValueError("h11 parser is unavailable") from exc

    connection = h11.Connection(h11.SERVER)
    connection.receive_data(head)
    event = connection.next_event()
    if not isinstance(event, h11.Request):
        raise ValueError("Invalid HTTP request line")

    method = event.method.decode("latin-1")
    target = event.target.decode("latin-1")
    version = f"HTTP/{event.http_version.decode('latin-1')}"
    headers = [
        (name.decode("latin-1"), value.decode("latin-1")) for name, value in list(event.headers)
    ]
    return method, target, version, headers


def _parse_request_head_httptools(
    head: bytes,
) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Parse HTTP request head using ``httptools`` for parity mode."""

    httptools, upgrade_exc_type = _get_httptools_backend()
    protocol = _HTTPToolsParserProtocol()
    parser = httptools.HttpRequestParser(protocol)
    protocol.bind_parser(parser)

    try:
        parser.feed_data(head)
    except Exception as exc:  # noqa: BLE001
        # httptools raises HttpParserUpgrade when a valid Upgrade request head
        # is parsed; treat this as success and continue with parsed fields.
        if not (isinstance(upgrade_exc_type, type) and isinstance(exc, upgrade_exc_type)):
            raise ValueError("Invalid HTTP request line") from exc

    if not protocol.method:
        raise ValueError("Invalid HTTP request line")
    return protocol.method, protocol.target, protocol.http_version, protocol.headers


def build_http_scope(
    request: HTTPRequest,
    *,
    client: ClientAddress,
    server: ServerAddress,
    root_path: str,
    is_tls: bool,
) -> Scope:
    """Build an ASGI HTTP scope from request metadata."""

    path, _, query = request.target.partition("?")
    decoded_path = unquote(path)
    raw_path = path.encode("latin-1")
    root_path_bytes = root_path.encode("latin-1")
    full_path = root_path + decoded_path
    full_raw_path = root_path_bytes + raw_path

    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": request.http_version.removeprefix("HTTP/"),
        "method": request.method,
        "scheme": "https" if is_tls else "http",
        "path": full_path,
        "raw_path": full_raw_path,
        "query_string": query.encode("latin-1"),
        "root_path": root_path,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in request.headers
        ],
        "client": client,
        "server": server,
        "state": {},
    }


async def run_http_asgi(
    app: ASGIApplication,
    scope: Scope,
    request_body: bytes,
) -> HTTPResponse:
    """Execute an ASGI app for HTTP scope and capture its response."""

    response = HTTPResponse()
    request_sent = False
    body_complete = False
    request_message: Message = {"type": "http.request", "body": request_body, "more_body": False}
    disconnect_message: Message = {"type": "http.disconnect"}

    async def receive() -> Message:
        nonlocal request_sent

        if not request_sent:
            request_sent = True
            return request_message
        return disconnect_message

    async def send(message: Message) -> None:
        nonlocal body_complete

        message_type = message["type"]
        if message_type == "http.response.start":
            response.status = int(message.get("status", 200))
            response.headers = list(message.get("headers", []))
            return

        if message_type == "http.response.body":
            if body_complete:
                return
            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            response.body_chunks.append(body)
            body_complete = not message.get("more_body", False)
            return

        raise RuntimeError(f"Unsupported HTTP ASGI message type: {message_type}")

    await app(scope, receive, send)
    return response


def append_default_response_headers(
    response: HTTPResponse,
    config: PalfreyConfig,
) -> None:
    """Add default response headers controlled by runtime configuration."""

    configured_headers = config.normalized_headers
    existing_headers = {name.lower() for name, _ in response.headers}
    configured_header_names = {name.lower() for name, _ in configured_headers}

    if (
        config.server_header
        and b"server" not in existing_headers
        and "server" not in configured_header_names
    ):
        response.headers.append((b"server", b"palfrey"))

    if (
        config.date_header
        and b"date" not in existing_headers
        and "date" not in configured_header_names
    ):
        response.headers.append((b"date", _http_date_header()))

    for name, value in configured_headers:
        response.headers.append((name.encode("latin-1"), value.encode("latin-1")))


def encode_http_response(response: HTTPResponse, keep_alive: bool) -> bytes:
    """Serialize a captured HTTP response to wire bytes."""

    reason = {
        200: b"OK",
        101: b"Switching Protocols",
        400: b"Bad Request",
        404: b"Not Found",
        500: b"Internal Server Error",
        503: b"Service Unavailable",
    }.get(response.status, b"OK")

    payload = b"".join(response.body_chunks)
    header_lines: list[bytes] = [f"HTTP/1.1 {response.status}".encode("ascii") + b" " + reason]

    has_content_length = False
    for name, value in response.headers:
        if name.lower() == b"content-length":
            has_content_length = True
        header_lines.append(name + b": " + value)

    if not has_content_length:
        header_lines.append(b"content-length: " + str(len(payload)).encode("ascii"))

    header_lines.append(b"connection: keep-alive" if keep_alive else b"connection: close")

    return b"\r\n".join(header_lines) + b"\r\n\r\n" + payload


def should_keep_alive(request: HTTPRequest, response: HTTPResponse) -> bool:
    """Evaluate HTTP keep-alive behavior from request and response headers."""

    request_connection = _normalize_connection_value(request.headers)
    response_connection = ""
    for name, value in response.headers:
        if name.lower() == b"connection":
            response_connection = value.decode("latin-1").lower()
            break

    if "close" in request_connection or "close" in response_connection:
        return False

    if request.http_version == "HTTP/1.0" and "keep-alive" not in request_connection:
        return False

    return True


def is_websocket_upgrade(request: HTTPRequest) -> bool:
    """Return whether the request asks for a WebSocket protocol upgrade."""

    return _is_websocket_upgrade(request.headers)


def requires_100_continue(request: HTTPRequest) -> bool:
    """Return whether request asks for ``100-continue`` expectation."""

    expect = _header_lookup(request.headers, "expect")
    if not expect:
        return False
    return expect.lower() == "100-continue"
