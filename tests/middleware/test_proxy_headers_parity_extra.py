"""Additional proxy header middleware parity tests."""

from __future__ import annotations

import asyncio

from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware
from palfrey.types import Message, Scope


async def _noop_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(_message: Message) -> None:
    return None


def test_proxy_headers_trusts_comma_separated_hosts() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "127.0.0.1, 10.0.0.1")
    scope: Scope = {
        "type": "http",
        "client": ("10.0.0.1", 5000),
        "scheme": "http",
        "headers": [(b"x-forwarded-for", b"198.51.100.1")],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert captured_scope["client"] == ("198.51.100.1", 5000)


def test_proxy_headers_updates_websocket_scope() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "*")
    scope: Scope = {
        "type": "websocket",
        "client": ("127.0.0.1", 1234),
        "scheme": "ws",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.9"),
            (b"x-forwarded-proto", b"wss"),
        ],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert captured_scope["client"] == ("203.0.113.9", 1234)
    assert captured_scope["scheme"] == "wss"


def test_proxy_headers_uses_first_forwarded_for_value() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "127.0.0.1")
    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 4321),
        "scheme": "http",
        "headers": [(b"x-forwarded-for", b"198.51.100.1, 198.51.100.2")],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert captured_scope["client"] == ("198.51.100.1", 4321)


def test_proxy_headers_uses_first_forwarded_proto_value() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "127.0.0.1")
    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 9999),
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"https, http")],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert captured_scope["scheme"] == "https"


def test_proxy_headers_ignores_invalid_forwarded_proto_values() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "127.0.0.1")
    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 7777),
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"ftp")],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert captured_scope["scheme"] == "http"


def test_proxy_headers_no_client_keeps_scope_unchanged() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "*")
    scope: Scope = {
        "type": "http",
        "scheme": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
    }

    asyncio.run(middleware(scope, _noop_receive, _noop_send))
    assert "client" not in captured_scope
    assert captured_scope["scheme"] == "http"
