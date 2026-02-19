from __future__ import annotations

import asyncio
import io
import sys

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
        "body": b"echo:",
        "more_body": True,
    }
    assert sent_messages[2] == {
        "type": "http.response.body",
        "body": b"hello world",
        "more_body": True,
    }
    assert sent_messages[3] == {
        "type": "http.response.body",
        "body": b"",
        "more_body": False,
    }
    assert captured_environ["REQUEST_METHOD"] == "POST"
    assert captured_environ["SCRIPT_NAME"] == "/root"
    assert captured_environ["PATH_INFO"] == "/hello world"
    assert captured_environ["QUERY_STRING"] == "x=1"
    assert captured_environ["REMOTE_ADDR"] == "127.0.0.1"
    assert captured_environ["SERVER_NAME"] == "127.0.0.1"
    assert captured_environ["SERVER_PORT"] == 8000
    assert captured_environ["HTTP_X_TOKEN"] == "abc"
    assert "CONTENT_LENGTH" not in captured_environ
    assert captured_environ["wsgi.errors"] is sys.stdout
    assert captured_environ["wsgi.multiprocess"] is True


def test_wsgi_adapter_merges_repeated_headers() -> None:
    scope = _http_scope()
    scope["headers"] = [(b"x-token", b"abc"), (b"x-token", b"def")]
    captured: dict[str, object] = {}

    def wsgi_app(environ, start_response):
        captured.update(environ)
        start_response("200 OK", [("content-type", "text/plain")])
        return [b"ok"]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        return None

    asyncio.run(WSGIAdapter(wsgi_app)(scope, receive, send))
    assert captured["HTTP_X_TOKEN"] == "abc,def"


def test_wsgi_adapter_raises_exc_info_after_response() -> None:
    def wsgi_app(environ, start_response):
        try:
            raise RuntimeError("wsgi-failure")
        except RuntimeError:
            start_response(
                "500 Internal Server Error",
                [("content-type", "text/plain")],
                sys.exc_info(),
            )
            return [b"error"]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        return None

    with pytest.raises(RuntimeError, match="wsgi-failure"):
        asyncio.run(WSGIAdapter(wsgi_app)(_http_scope(), receive, send))


def test_wsgi_adapter_closes_iterable_result() -> None:
    closed: list[bool] = []

    class Result:
        def __iter__(self):
            yield b"chunk"

        def close(self) -> None:
            closed.append(True)

    def wsgi_app(environ, start_response):
        start_response("200 OK", [("content-type", "text/plain")])
        return Result()

    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(WSGIAdapter(wsgi_app)(_http_scope(), receive, send))
    assert closed == [True]


def test_wsgi_adapter_propagates_wsgi_exception() -> None:
    def wsgi_app(environ, start_response):
        raise RuntimeError("Something went wrong")

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        return None

    with pytest.raises(RuntimeError, match="Something went wrong"):
        asyncio.run(WSGIAdapter(wsgi_app)(_http_scope(), receive, send))


def test_build_wsgi_environ_encoding_parity() -> None:
    scope: dict[str, object] = {
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "scheme": "http",
        "raw_path": b"/\xe6\x96\x87%2Fall",
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/文/all",
        "root_path": "/文",
        "client": None,
        "server": None,
        "query_string": b"a=123&b=456",
        "headers": [(b"key", b"value1"), (b"key", b"value2")],
        "extensions": {},
    }
    environ = WSGIAdapter._build_wsgi_environ(scope, io.BytesIO(b"").read())
    assert environ["SCRIPT_NAME"] == "/文".encode().decode("latin-1")
    assert environ["PATH_INFO"] == b"/all".decode("latin-1")
    assert environ["HTTP_KEY"] == "value1,value2"
