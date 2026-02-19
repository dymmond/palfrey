from __future__ import annotations

import asyncio
import http
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from palfrey.acceleration import parse_request_head
from palfrey.http_date import cached_http_date_header

if TYPE_CHECKING:
    from palfrey.config import PalfreyConfig
    from palfrey.types import (
        ASGIApplication,
        ClientAddress,
        Headers,
        Message,
        Scope,
        ServerAddress,
    )

# Import types for internal use within this module
from palfrey.types import (
    ASGIApplication,
    ClientAddress,
    Headers,
    Message,
    Scope,
    ServerAddress,
)


@dataclass(slots=True)
class HTTPRequest:
    """
    Data container for a parsed HTTP request, including headers and body content.

    This class normalizes the body representation into both a contiguous byte
    string and a list of chunks, facilitating easier processing for both
    synchronous logic and asynchronous streaming.

    Attributes:
        method (str): The HTTP method (e.g., 'GET', 'POST').
        target (str): The full request URI or path.
        http_version (str): The protocol version (e.g., 'HTTP/1.1').
        headers (list[tuple[str, str]]): List of header name-value pairs as strings.
        body (bytes): The complete request body as a single byte string.
        body_chunks (list[bytes]): The body split into chunks, as received
            from the wire.
    """

    method: str
    target: str
    http_version: str
    headers: list[tuple[str, str]]
    body: bytes
    body_chunks: list[bytes] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Synchronize the body and body_chunks attributes after initialization.
        """
        if self.body_chunks:
            self.body = b"".join(self.body_chunks)
            return
        # Ensure body_chunks is always a list for consistent iteration
        self.body_chunks = [self.body] if self.body else [b""]


@dataclass(slots=True)
class HTTPResponse:
    """
    Representation of an outgoing HTTP response constructed from ASGI events.

    This object acts as a collector for headers and body chunks sent by the
    application before they are serialized to the network socket.

    Attributes:
        status (int): HTTP status code (default 500).
        headers (Headers): List of header tuples in bytes.
        body_chunks (list[bytes]): Fragments of the response body.
        chunked_encoding (bool): Whether the response uses Transfer-Encoding: chunked.
        suppress_body (bool): If True, the body is omitted (e.g., for HEAD requests).
    """

    status: int = 500
    headers: Headers = field(default_factory=list)
    body_chunks: list[bytes] = field(default_factory=list)
    chunked_encoding: bool = False
    suppress_body: bool = False


class _HTTPToolsParserProtocol:
    """
    Callback handler for the C-based httptools request parser.

    This class implements the required interface for httptools, capturing
    URL fragments, headers, and protocol metadata as they are parsed from
    incoming byte streams.
    """

    __slots__ = ("method", "target", "http_version", "headers", "_parser")

    def __init__(self) -> None:
        """
        Initialize the parser protocol state.
        """
        self.method = ""
        self.target = ""
        self.http_version = "HTTP/1.1"
        self.headers: list[tuple[str, str]] = []
        self._parser: Any = None

    def bind_parser(self, parser: Any) -> None:
        """
        Link the protocol to the specific parser instance for metadata extraction.

        Args:
            parser (Any): The httptools.HttpRequestParser instance.
        """
        self._parser = parser

    def on_url(self, url: bytes) -> None:
        """
        Captured during the request line parsing.

        Args:
            url (bytes): Raw URL bytes.
        """
        self.target = url.decode("latin-1")

    def on_header(self, name: bytes, value: bytes) -> None:
        """
        Captured for every header field.

        Args:
            name (bytes): Header field name.
            value (bytes): Header field value.
        """
        self.headers.append((name.decode("latin-1"), value.decode("latin-1")))

    def on_headers_complete(self) -> None:
        """
        Finalize the request line and metadata once headers are finished.
        """
        parser = self._parser
        self.http_version = f"HTTP/{parser.get_http_version()}"
        self.method = parser.get_method().decode("latin-1")

    def on_message_complete(self) -> None:
        """
        Notification that the entire request head has been processed.
        """
        return None


_HTTPTOOLS_MODULE: Any | None = None
_HTTPTOOLS_UPGRADE_EXC_TYPE: type[BaseException] | None = None


def _get_httptools_backend() -> tuple[Any, type[BaseException] | None]:
    """
    Load the httptools library and its specific exception types lazily.

    Returns:
        tuple: (httptools module, Upgrade exception class).
    """
    global _HTTPTOOLS_MODULE, _HTTPTOOLS_UPGRADE_EXC_TYPE

    if _HTTPTOOLS_MODULE is not None:
        return _HTTPTOOLS_MODULE, _HTTPTOOLS_UPGRADE_EXC_TYPE

    try:
        import httptools
    except ImportError as exc:
        raise ValueError("httptools parser is unavailable") from exc

    upgrade_exc = getattr(getattr(httptools, "parser", None), "errors", None)
    upgrade_exc_type = getattr(upgrade_exc, "HttpParserUpgrade", None)
    if not isinstance(upgrade_exc_type, type):
        upgrade_exc_type = None

    _HTTPTOOLS_MODULE = httptools
    _HTTPTOOLS_UPGRADE_EXC_TYPE = upgrade_exc_type
    return httptools, upgrade_exc_type


def _http_date_header() -> bytes:
    """
    Retrieve a current HTTP-formatted date string for response headers.
    """
    return cached_http_date_header()


def _normalize_connection_value(headers: list[tuple[str, str]]) -> str:
    """
    Helper to extract and normalize the 'Connection' header value.
    """
    for name, value in headers:
        if name.lower() == "connection":
            return value.lower()
    return ""


def _is_websocket_upgrade(headers: list[tuple[str, str]]) -> bool:
    """
    Check headers to determine if the client is requesting a WebSocket upgrade.
    """
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
    """
    Case-insensitive search for a header value in a list of string tuples.
    """
    for name, value in headers:
        if name.lower() == key.lower():
            return value
    return None


async def _read_chunked_body_chunks(
    reader: asyncio.StreamReader,
    body_limit: int,
) -> list[bytes]:
    """
    Read an HTTP body formatted with chunked transfer encoding.

    Args:
        reader (asyncio.StreamReader): The source socket reader.
        body_limit (int): Maximum total bytes allowed for the body.

    Returns:
        list[bytes]: A list of body chunks.

    Raises:
        ValueError: If the encoding is malformed or the limit is exceeded.
    """
    body_chunks: list[bytes] = []
    total = 0

    while True:
        chunk_size_line = await reader.readline()
        if not chunk_size_line:
            raise ValueError("Unexpected EOF while reading chunked body")

        # Split on semicolon to ignore chunk extensions
        chunk_size_text = chunk_size_line.split(b";", 1)[0].strip()
        try:
            chunk_size = int(chunk_size_text, 16)
        except ValueError as exc:
            raise ValueError("Malformed chunked encoding size") from exc

        if chunk_size == 0:
            # Last chunk is 0 followed by CRLF
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

    return body_chunks


async def _read_content_length_body_chunks(
    reader: asyncio.StreamReader,
    content_length: int,
    body_limit: int,
) -> list[bytes]:
    """
    Read a fixed-size body from the stream into manageable chunks.

    Args:
        reader (asyncio.StreamReader): The socket reader.
        content_length (int): Total expected bytes from Content-Length header.
        body_limit (int): Maximum bytes allowed by server configuration.

    Returns:
        list[bytes]: List of body fragments.
    """
    if content_length > body_limit:
        raise ValueError("HTTP body exceeds configured limit")
    if content_length <= 0:
        return [b""]

    remaining = content_length
    chunks: list[bytes] = []
    read_size = 65_536
    while remaining > 0:
        chunk = await reader.readexactly(min(read_size, remaining))
        chunks.append(chunk)
        remaining -= len(chunk)
    return chunks


async def read_http_request(
    reader: asyncio.StreamReader,
    *,
    max_head_size: int = 1_048_576,
    body_limit: int = 4_194_304,
    parser_mode: str = "auto",
) -> HTTPRequest | None:
    """
    Read and parse a full HTTP request (head and body) from the reader.

    Args:
        reader (asyncio.StreamReader): The client stream reader.
        max_head_size (int): Max allowed bytes for the request line and headers.
        body_limit (int): Max allowed bytes for the body.
        parser_mode (str): Choice of parser ('httptools', 'h11', or 'auto').

    Returns:
        HTTPRequest | None: The parsed request, or None if the client disconnected.
    """
    try:
        # Read until the double CRLF signaling the end of headers
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

    # Determine body reading strategy
    body_chunks: list[bytes] = [b""]
    if "chunked" in transfer_encoding:
        body_chunks = await _read_chunked_body_chunks(reader, body_limit)
    else:
        body_chunks = await _read_content_length_body_chunks(reader, content_length, body_limit)
    body = b"".join(body_chunks)

    return HTTPRequest(
        method=method,
        target=target,
        http_version=version,
        headers=headers,
        body=body,
        body_chunks=body_chunks,
    )


def _parse_request_head(
    head: bytes,
    parser_mode: str,
) -> tuple[str, str, str, list[tuple[str, str]]]:
    """
    Dispatch head parsing to the chosen backend.
    """
    if parser_mode == "h11":
        return _parse_request_head_h11(head)
    if parser_mode == "httptools":
        return _parse_request_head_httptools(head)

    # Auto-detection logic: try native, then httptools, then h11
    try:
        return parse_request_head(head)
    except ValueError:
        with suppress(ValueError):
            return _parse_request_head_httptools(head)
        return _parse_request_head_h11(head)


def _parse_request_head_h11(
    head: bytes,
) -> tuple[str, str, str, list[tuple[str, str]]]:
    """
    Use the pure-python h11 library to parse request headers.
    """
    try:
        import h11
    except ImportError as exc:
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
    """
    Use the high-performance httptools library to parse request headers.
    """
    httptools, upgrade_exc_type = _get_httptools_backend()
    protocol = _HTTPToolsParserProtocol()
    parser = httptools.HttpRequestParser(protocol)
    protocol.bind_parser(parser)

    try:
        parser.feed_data(head)
    except Exception as exc:
        # Handle the specific case where httptools signals a protocol upgrade
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
    """
    Convert an internal HTTPRequest into an ASGI 3.0 scope dictionary.

    Args:
        request (HTTPRequest): Parsed request data.
        client (ClientAddress): IP and port of the client.
        server (ServerAddress): IP and port of the server.
        root_path (str): The mounting point of the application.
        is_tls (bool): True if connection is encrypted.

    Returns:
        Scope: A dictionary conforming to the ASGI HTTP specification.
    """
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
    request_body: bytes | list[bytes],
    *,
    expect_100_continue: bool = False,
    on_100_continue: Callable[[], Awaitable[None]] | None = None,
) -> HTTPResponse:
    """
    Orchestrate the ASGI request/response lifecycle.

    This function wraps the application call, providing the 'receive' and 'send'
    coroutines required by the ASGI spec.

    Args:
        app (ASGIApplication): The user-provided ASGI application.
        scope (Scope): The connection scope.
        request_body (bytes | list[bytes]): The input body.
        expect_100_continue (bool): If the client expects a 100-Continue response.
        on_100_continue (Callable): Callback to send the 100 status code.

    Returns:
        HTTPResponse: The resulting response state.
    """
    response = HTTPResponse()
    body_chunks = request_body if isinstance(request_body, list) else [request_body]
    if not body_chunks:
        body_chunks = [b""]

    response_started = False
    response_complete = False
    waiting_for_100_continue = expect_100_continue
    body_index = 0
    message_complete = asyncio.Event()
    chunked_encoding: bool | None = None
    expected_content_length = 0

    async def _send_internal_server_error() -> None:
        """
        Internal helper to create a 500 response if the app crashes before sending headers.
        """
        nonlocal response_started, response_complete, chunked_encoding, expected_content_length
        response_started = True
        response_complete = True
        chunked_encoding = False
        expected_content_length = 0
        response.status = 500
        response.headers = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", b"21"),
            (b"connection", b"close"),
        ]
        response.body_chunks = [] if scope.get("method") == "HEAD" else [b"Internal Server Error"]
        response.chunked_encoding = False
        response.suppress_body = scope.get("method") == "HEAD"
        message_complete.set()

    async def receive() -> Message:
        """
        ASGI receive callable for streaming the request body to the app.
        """
        nonlocal waiting_for_100_continue, body_index

        if waiting_for_100_continue:
            waiting_for_100_continue = False
            if on_100_continue is not None:
                await on_100_continue()

        if body_index < len(body_chunks):
            body = body_chunks[body_index]
            body_index += 1
            return {
                "type": "http.request",
                "body": body,
                "more_body": body_index < len(body_chunks),
            }

        await message_complete.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        """
        ASGI send callable for streaming the response from the app to the server.
        """
        nonlocal response_started, response_complete, waiting_for_100_continue
        nonlocal chunked_encoding, expected_content_length

        message_type = message["type"]
        if not response_started:
            if message_type != "http.response.start":
                msg = "Expected ASGI message 'http.response.start', but got '%s'."
                raise RuntimeError(msg % message_type)

            response_started = True
            waiting_for_100_continue = False

            response.status = int(message.get("status", 200))
            response.headers = [
                (_coerce_header_bytes(name), _coerce_header_bytes(value))
                for name, value in list(message.get("headers", []))
            ]
            response.suppress_body = scope.get("method") == "HEAD"

            # Parse headers for content-length or transfer-encoding
            for name, value in response.headers:
                lowered_name = name.lower()
                lowered_value = value.lower()
                if lowered_name == b"content-length" and chunked_encoding is None:
                    try:
                        expected_content_length = int(value.decode("latin-1"))
                    except ValueError as exc:
                        raise RuntimeError("Invalid Content-Length header.") from exc
                    chunked_encoding = False
                elif lowered_name == b"transfer-encoding" and lowered_value == b"chunked":
                    chunked_encoding = True
                    expected_content_length = 0

            # Default to chunked if no length is provided
            if (
                chunked_encoding is None
                and scope.get("method") != "HEAD"
                and response.status not in {204, 304}
            ):
                chunked_encoding = True
                response.headers.append((b"transfer-encoding", b"chunked"))

            response.chunked_encoding = bool(chunked_encoding)
            return

        if response_complete:
            msg = "Unexpected ASGI message '%s' sent, after response already completed."
            raise RuntimeError(msg % message_type)

        if message_type != "http.response.body":
            msg = "Expected ASGI message 'http.response.body', but got '%s'."
            raise RuntimeError(msg % message_type)

        body = message.get("body", b"")
        if not isinstance(body, bytes):
            body = bytes(body)
        more_body = bool(message.get("more_body", False))

        if response.suppress_body:
            body = b""
            expected_content_length = 0
        elif chunked_encoding:
            response.body_chunks.append(body)
        else:
            body_size = len(body)
            if body_size > expected_content_length:
                raise RuntimeError("Response content longer than Content-Length")
            expected_content_length -= body_size
            response.body_chunks.append(body)

        if not more_body:
            if not chunked_encoding and expected_content_length != 0:
                raise RuntimeError("Response content shorter than Content-Length")
            response_complete = True
            message_complete.set()

    try:
        result = await app(scope, receive, send)
    except BaseException as exc:
        if not response_started:
            await _send_internal_server_error()
        elif isinstance(exc, RuntimeError):
            raise
        else:
            raise RuntimeError("Exception in ASGI application") from exc
    else:
        if result is not None:
            raise RuntimeError(f"ASGI callable should return None, but returned '{result}'.")
        if not response_started:
            await _send_internal_server_error()
        elif not response_complete:
            raise RuntimeError("ASGI callable returned without completing response.")
    return response


def _coerce_header_bytes(value: object) -> bytes:
    """
    Ensure header values are in raw byte format.
    """
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value).encode("latin-1")


def append_default_response_headers(
    response: HTTPResponse,
    config: PalfreyConfig,
    *,
    default_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    """
    Apply configured default headers (like 'Server' or 'Date') to the response.

    Args:
        response (HTTPResponse): Response to modify.
        config (PalfreyConfig): Application configuration.
        default_headers (list[tuple[bytes, bytes]] | None): Cached list of headers.
    """
    existing_headers = {name.lower() for name, _ in response.headers}

    if default_headers is not None:
        for name, value in default_headers:
            lowered_name = name.lower()
            if lowered_name in existing_headers:
                continue
            response.headers.append((name, value))
            existing_headers.add(lowered_name)
        return

    configured_headers = config.normalized_headers
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
    """
    Serialize the HTTPResponse object into raw wire bytes for network transmission.

    Args:
        response (HTTPResponse): Response data collected from the app.
        keep_alive (bool): Whether the connection should remain open.

    Returns:
        bytes: Serialized HTTP response.
    """
    try:
        reason = http.HTTPStatus(response.status).phrase.encode("ascii")
    except ValueError:
        reason = b""

    # Status line
    header_lines: list[bytes] = [f"HTTP/1.1 {response.status}".encode("ascii") + b" " + reason]

    has_content_length = False
    has_transfer_encoding = False
    has_connection = False
    for name, value in response.headers:
        lowered_name = name.lower()
        if lowered_name == b"content-length":
            has_content_length = True
        elif lowered_name == b"transfer-encoding" and value.lower() == b"chunked":
            has_transfer_encoding = True
        elif lowered_name == b"connection":
            has_connection = True
        header_lines.append(name + b": " + value)

    payload_chunks = [] if response.suppress_body else response.body_chunks
    payload = b"".join(payload_chunks)

    # Automatic Content-Length insertion
    if not has_content_length and not has_transfer_encoding:
        header_lines.append(b"content-length: " + str(len(payload)).encode("ascii"))

    # Connection persistence signaling
    if not has_connection:
        header_lines.append(b"connection: keep-alive" if keep_alive else b"connection: close")

    # Serialize chunked body if applicable
    if has_transfer_encoding:
        chunked_chunks: list[bytes] = []
        for chunk in payload_chunks:
            if not chunk:
                continue
            chunked_chunks.append(f"{len(chunk):x}\r\n".encode("ascii"))
            chunked_chunks.append(chunk)
            chunked_chunks.append(b"\r\n")
        chunked_chunks.append(b"0\r\n\r\n")
        payload = b"".join(chunked_chunks)

    return b"\r\n".join(header_lines) + b"\r\n\r\n" + payload


def should_keep_alive(request: HTTPRequest, response: HTTPResponse) -> bool:
    """
    Determine if the TCP connection should persist based on headers and protocol version.
    """
    request_connection = _normalize_connection_value(request.headers)
    response_connection = ""
    for name, value in response.headers:
        if name.lower() == b"connection":
            response_connection = value.decode("latin-1").lower()
            break

    if "close" in request_connection or "close" in response_connection:
        return False

    # HTTP/1.0 requires explicit Keep-Alive
    if request.http_version == "HTTP/1.0" and "keep-alive" not in request_connection:
        return False

    return True


def is_websocket_upgrade(request: HTTPRequest) -> bool:
    """
    Check if the request is a WebSocket handshake.
    """
    return _is_websocket_upgrade(request.headers)


def requires_100_continue(request: HTTPRequest) -> bool:
    """
    Verify if the client is waiting for a '100 Continue' response before sending the body.
    """
    expect = _header_lookup(request.headers, "expect")
    if not expect:
        return False
    return expect.lower() == "100-continue"
