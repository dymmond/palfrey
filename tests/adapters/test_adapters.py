"""Tests for ASGI2 and WSGI adapter behavior."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.adapters import ASGI2Adapter, WSGIAdapter


def _http_scope() -> dict[str, object]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/hello world",
        "query_string": b"x=1",
        "root_path": "/root",
        "headers": [(b"content-type", b"text/plain"), (b"x-token", b"abc")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }


def test_asgi2_adapter_invokes_inner_application() -> None:
    calls: list[str] = []
    sent_messages: list[dict[str, object]] = []

    def asgi2_app(scope: dict[str, object]):
        async def instance(receive, send):
            calls.append(scope["path"])  # type: ignore[arg-type]
            request = await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send(
                {
                    "type": "http.response.body",
                    "body": request.get("body", b""),
                    "more_body": False,
                }
            )

        return instance

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"payload", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)

    adapter = ASGI2Adapter(asgi2_app)
    asyncio.run(adapter(_http_scope(), receive, send))

    assert calls == ["/hello world"]
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[1]["body"] == b"payload"


def test_wsgi_adapter_rejects_non_http_scope() -> None:
    async def receive() -> dict[str, object]:
        return {"type": "websocket.connect"}

    async def send(_: dict[str, object]) -> None:
        return None

    adapter = WSGIAdapter(lambda environ, start_response: [b"ok"])
    with pytest.raises(RuntimeError, match="only supports HTTP scopes"):
        asyncio.run(adapter({"type": "websocket"}, receive, send))


def test_wsgi_adapter_translates_scope_and_streams_response() -> None:
    captured_environ: dict[str, object] = {}
    sent_messages: list[dict[str, object]] = []

    def wsgi_app(environ: dict[str, object], start_response):
        captured_environ.update(environ)
        start_response("201 Created", [("content-type", "text/plain"), ("x-app", "palfrey")])
        return [b"echo:", environ["wsgi.input"].read()]  # type: ignore[index]

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    queue.put_nowait({"type": "http.request", "body": b"hello", "more_body": True})
    queue.put_nowait({"type": "http.request", "body": b" world", "more_body": False})

    async def receive() -> dict[str, object]:
        return await queue.get()

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)

    adapter = WSGIAdapter(wsgi_app)
    asyncio.run(adapter(_http_scope(), receive, send))

    assert sent_messages[0] == {
        "type": "http.response.start",
        "status": 201,
        "headers": [(b"content-type", b"text/plain"), (b"x-app", b"palfrey")],
    }
    assert sent_messages[1] == {
        "type": "http.response.body",
        "body": b"echo:hello world",
        "more_body": False,
    }
    assert captured_environ["REQUEST_METHOD"] == "POST"
    assert captured_environ["SCRIPT_NAME"] == "/root"
    assert captured_environ["PATH_INFO"] == "/hello%20world"
    assert captured_environ["QUERY_STRING"] == "x=1"
    assert captured_environ["REMOTE_ADDR"] == "127.0.0.1"
    assert captured_environ["REMOTE_PORT"] == "1234"
    assert captured_environ["SERVER_NAME"] == "127.0.0.1"
    assert captured_environ["SERVER_PORT"] == "8000"
    assert captured_environ["HTTP_X_TOKEN"] == "abc"
    assert captured_environ["CONTENT_LENGTH"] == "11"
