"""Lifecycle logging parity tests for message logger middleware."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.middleware.message_logger import MessageLoggerMiddleware


def test_message_logger_emits_started_receive_send_completed(caplog) -> None:
    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    with caplog.at_level(5, logger="palfrey.asgi"):
        asyncio.run(MessageLoggerMiddleware(app)({"type": "http"}, receive, send))

    assert len(sent_messages) == 2

    messages = [record.msg % record.args for record in caplog.records]
    assert sum("ASGI [1] Started" in message for message in messages) == 1
    assert sum("ASGI [1] Receive" in message for message in messages) == 1
    assert sum("ASGI [1] Send" in message for message in messages) == 2
    assert sum("ASGI [1] Completed" in message for message in messages) == 1


def test_message_logger_emits_raised_exception(caplog) -> None:
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    with caplog.at_level(5, logger="palfrey.asgi"):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(MessageLoggerMiddleware(app)({"type": "http"}, receive, send))

    messages = [record.msg % record.args for record in caplog.records]
    assert sum("ASGI [1] Raised exception" in message for message in messages) == 1
