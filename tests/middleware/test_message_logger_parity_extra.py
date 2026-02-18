"""Additional message logger middleware tests."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.middleware.message_logger import MessageLoggerMiddleware, message_with_placeholders
from palfrey.types import Message


def test_message_logger_masks_websocket_bytes_payload(caplog) -> None:
    async def app(scope, receive, send):
        msg = await receive()
        assert msg["bytes"] == b"binary"
        await send({"type": "websocket.send", "bytes": b"reply"})

    middleware = MessageLoggerMiddleware(app, logger_name="tests.asgi.ws")

    async def receive() -> Message:
        return {"type": "websocket.receive", "bytes": b"binary"}

    async def send(_message: Message) -> None:
        return None

    with caplog.at_level(5, logger="tests.asgi.ws"):
        asyncio.run(middleware({"type": "websocket"}, receive, send))

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "<6 bytes>" in logs
    assert "<5 bytes>" in logs


def test_message_logger_wraps_send_without_mutating_message() -> None:
    observed: list[Message] = []

    async def app(scope, receive, send):
        await receive()
        message = {"type": "http.response.body", "body": b"ok", "more_body": False}
        await send(message)
        observed.append(message)

    middleware = MessageLoggerMiddleware(app, logger_name="tests.asgi.mutate")

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: Message) -> None:
        return None

    asyncio.run(middleware({"type": "http"}, receive, send))
    assert observed[0]["body"] == b"ok"


def test_message_logger_masks_empty_body_as_zero_bytes() -> None:
    masked = message_with_placeholders({"type": "http.request", "body": b""})
    assert masked["body"] == "<0 bytes>"


def test_message_logger_logs_raised_exception(caplog) -> None:
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    middleware = MessageLoggerMiddleware(app, logger_name="tests.asgi.exc")

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: Message) -> None:
        return None

    with caplog.at_level(5, logger="tests.asgi.exc"):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(middleware({"type": "http"}, receive, send))

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "Raised exception" in logs
