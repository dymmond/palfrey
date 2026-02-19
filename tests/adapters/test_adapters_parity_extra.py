from __future__ import annotations

import asyncio

from palfrey.adapters import WSGIAdapter


def _scope() -> dict[str, object]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"text/plain")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }


def test_wsgi_adapter_defaults_to_500_when_start_response_not_called() -> None:
    sent: list[dict[str, object]] = []

    def wsgi_app(environ, start_response):
        return [b"payload"]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(WSGIAdapter(wsgi_app)(_scope(), receive, send))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 500
    assert sent[1]["body"] == b"payload"


def test_wsgi_adapter_passes_through_multiple_chunks() -> None:
    sent: list[dict[str, object]] = []

    def wsgi_app(environ, start_response):
        start_response("200 OK", [("content-type", "text/plain")])
        return [b"hello", b" ", b"world"]

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    queue.put_nowait({"type": "http.request", "body": b"", "more_body": False})

    async def receive() -> dict[str, object]:
        return await queue.get()

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(WSGIAdapter(wsgi_app)(_scope(), receive, send))
    assert sent[1]["body"] == b"hello world"
