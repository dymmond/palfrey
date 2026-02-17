"""HTTP/1.1 protocol handling for Palfrey."""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from email.utils import format_datetime
from urllib.parse import unquote

from palfrey.acceleration import parse_request_head
from palfrey.config import PalfreyConfig
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
    headers: Headers | None = None
    body_chunks: list[bytes] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = []
        if self.body_chunks is None:
            self.body_chunks = []


def _http_date_header() -> bytes:
    now = dt.datetime.now(dt.timezone.utc)
    return format_datetime(now, usegmt=True).encode("latin-1")


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


async def read_http_request(
    reader: asyncio.StreamReader,
    *,
    max_head_size: int = 1_048_576,
    body_limit: int = 4_194_304,
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

    method, target, version, headers = parse_request_head(head)

    content_length = 0
    for name, value in headers:
        if name.lower() == "content-length":
            content_length = int(value)
            break

    if content_length > body_limit:
        raise ValueError("HTTP body exceeds configured limit")

    body = b""
    if content_length > 0:
        body = await reader.readexactly(content_length)

    return HTTPRequest(method=method, target=target, http_version=version, headers=headers, body=body)


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

    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": request.http_version.removeprefix("HTTP/"),
        "method": request.method,
        "scheme": "https" if is_tls else "http",
        "path": decoded_path,
        "raw_path": path.encode("latin-1"),
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
    body_sent = False

    receive_queue: asyncio.Queue[Message] = asyncio.Queue()
    await receive_queue.put({"type": "http.request", "body": request_body, "more_body": False})

    async def receive() -> Message:
        return await receive_queue.get()

    async def send(message: Message) -> None:
        nonlocal body_sent

        message_type = message["type"]
        if message_type == "http.response.start":
            response.status = int(message.get("status", 200))
            response.headers = list(message.get("headers", []))
            return

        if message_type == "http.response.body":
            if body_sent:
                return
            body = message.get("body", b"")
            response.body_chunks.append(body)
            body_sent = not message.get("more_body", False)
            return

        raise RuntimeError(f"Unsupported HTTP ASGI message type: {message_type}")

    await app(scope, receive, send)
    return response


def append_default_response_headers(
    response: HTTPResponse,
    config: PalfreyConfig,
) -> None:
    """Add default response headers controlled by runtime configuration."""

    existing_headers = {name.lower() for name, _ in response.headers}

    if config.server_header and b"server" not in existing_headers:
        response.headers.append((b"server", b"palfrey"))

    if config.date_header and b"date" not in existing_headers:
        response.headers.append((b"date", _http_date_header()))

    for name, value in config.normalized_headers:
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
