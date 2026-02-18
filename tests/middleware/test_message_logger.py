"""Message logger middleware tests."""

from __future__ import annotations

import asyncio
import logging

from palfrey.middleware.message_logger import MessageLoggerMiddleware
from palfrey.types import Message


def test_message_logger_masks_binary_and_body_payloads(caplog) -> None:
    received: list[Message] = []

    async def app(scope, receive, send):
        msg = await receive()
        received.append(msg)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"done", "more_body": False})

    middleware = MessageLoggerMiddleware(app, logger_name="tests.asgi")

    async def receive() -> Message:
        return {"type": "http.request", "body": b"hello", "more_body": False}

    async def send(_message: Message) -> None:
        return None

    with caplog.at_level(logging.DEBUG, logger="tests.asgi"):
        asyncio.run(middleware({"type": "http"}, receive, send))

    assert received
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "<5 bytes>" in logs
    assert "ASGI send" in logs
