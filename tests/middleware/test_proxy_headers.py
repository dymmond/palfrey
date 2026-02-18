"""Proxy headers middleware tests."""

from __future__ import annotations

import asyncio

from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware
from palfrey.types import Message, Scope


async def _noop_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def test_proxy_headers_updates_scope_for_trusted_client() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "127.0.0.1")

    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "headers": [
            (b"x-forwarded-for", b"198.51.100.10"),
            (b"x-forwarded-proto", b"https"),
        ],
    }

    async def send(_message: Message) -> None:
        return None

    asyncio.run(middleware(scope, _noop_receive, send))

    assert captured_scope["client"] == ("198.51.100.10", 12345)
    assert captured_scope["scheme"] == "https"


def test_proxy_headers_ignored_for_untrusted_client() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "10.0.0.1")
    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 1000),
        "scheme": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
    }

    async def send(_message: Message) -> None:
        return None

    asyncio.run(middleware(scope, _noop_receive, send))

    assert captured_scope["client"] == ("127.0.0.1", 1000)


def test_proxy_headers_supports_wildcard_trust() -> None:
    captured_scope: Scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)

    middleware = ProxyHeadersMiddleware(app, "*")
    scope: Scope = {
        "type": "http",
        "client": ("203.0.113.5", 1000),
        "scheme": "http",
        "headers": [(b"x-forwarded-for", b"192.0.2.20")],
    }

    async def send(_message: Message) -> None:
        return None

    asyncio.run(middleware(scope, _noop_receive, send))

    assert captured_scope["client"] == ("192.0.2.20", 1000)


def test_proxy_headers_does_not_modify_non_http_scopes() -> None:
    called = asyncio.Event()

    async def app(scope, receive, send):
        assert scope["type"] == "lifespan"
        called.set()

    middleware = ProxyHeadersMiddleware(app, "*")

    async def send(_message: Message) -> None:
        return None

    asyncio.run(middleware({"type": "lifespan"}, _noop_receive, send))
    assert called.is_set()
