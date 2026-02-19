"""Lifespan manager tests."""

from __future__ import annotations

import asyncio

import pytest

from palfrey.lifespan import LifespanManager, LifespanUnsupportedError


def test_lifespan_startup_and_shutdown_success() -> None:
    events: list[str] = []

    async def app(scope, receive, send):
        assert scope["type"] == "lifespan"
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                events.append("startup")
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                events.append("shutdown")
                await send({"type": "lifespan.shutdown.complete"})
                return

    manager = LifespanManager(app)

    async def scenario() -> None:
        await manager.startup()
        await manager.shutdown()

    asyncio.run(scenario())
    assert events == ["startup", "shutdown"]


def test_lifespan_startup_failure_raises() -> None:
    async def app(scope, receive, send):
        message = await receive()
        assert message["type"] == "lifespan.startup"
        await send({"type": "lifespan.startup.failed", "message": "boom"})

    manager = LifespanManager(app)

    async def scenario() -> None:
        await manager.startup()

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(scenario())


def test_lifespan_startup_raises_unsupported_when_app_does_not_emit_messages() -> None:
    async def app(scope, receive, send):
        raise RuntimeError("unsupported")

    manager = LifespanManager(app)

    async def scenario() -> None:
        await manager.startup()

    with pytest.raises(LifespanUnsupportedError, match="unsupported"):
        asyncio.run(scenario())
