"""ASGI lifespan protocol support."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field

from palfrey.logging_config import get_logger
from palfrey.types import ASGIApplication, Message, Scope

logger = get_logger("palfrey.lifespan")


class LifespanUnsupportedError(RuntimeError):
    """Raised when an app does not implement ASGI lifespan messaging."""


class LifespanStartupFailedError(RuntimeError):
    """Raised when an app explicitly reports ``lifespan.startup.failed``."""


@dataclass(slots=True)
class LifespanManager:
    """Coordinate ASGI lifespan startup and shutdown events.

    The manager runs the lifespan scope in a dedicated task and exchanges events
    through asyncio queues.
    """

    app: ASGIApplication
    _receive_queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    _send_queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    _task: asyncio.Task[None] | None = None

    async def _receive(self) -> Message:
        return await self._receive_queue.get()

    async def _send(self, message: Message) -> None:
        await self._send_queue.put(message)

    async def _run_lifespan(self) -> None:
        scope: Scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "state": {},
        }
        await self.app(scope, self._receive, self._send)

    async def _next_lifespan_message(self) -> Message:
        """Wait for a lifespan response or an early task failure."""

        if self._task is None:
            raise RuntimeError("Lifespan task is not running.")

        message_task = asyncio.create_task(self._send_queue.get())
        done, pending = await asyncio.wait(
            {message_task, self._task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for pending_task in pending:
            if pending_task is self._task:
                continue
            pending_task.cancel()
            with suppress(asyncio.CancelledError):
                await pending_task

        if message_task in done:
            return message_task.result()

        assert self._task in done
        exception = self._task.exception()
        if exception is None:
            raise LifespanUnsupportedError("ASGI lifespan protocol appears unsupported.")
        raise LifespanUnsupportedError("ASGI lifespan protocol appears unsupported.") from exception

    async def startup(self) -> None:
        """Trigger and await application startup completion.

        Raises:
            RuntimeError: If startup fails.
        """

        if self._task is None:
            self._task = asyncio.create_task(self._run_lifespan())

        await self._receive_queue.put({"type": "lifespan.startup"})

        message = await self._next_lifespan_message()
        message_type = message["type"]

        if message_type == "lifespan.startup.complete":
            logger.debug("Lifespan startup completed")
            return

        if message_type == "lifespan.startup.failed":
            raise LifespanStartupFailedError(message.get("message", "Lifespan startup failed"))

        raise RuntimeError(f"Unexpected lifespan startup message: {message_type}")

    async def shutdown(self) -> None:
        """Trigger and await application shutdown completion."""

        if self._task is None:
            return

        await self._receive_queue.put({"type": "lifespan.shutdown"})
        message = await self._next_lifespan_message()

        message_type = message["type"]
        if message_type not in {"lifespan.shutdown.complete", "lifespan.shutdown.failed"}:
            raise RuntimeError(f"Unexpected lifespan shutdown message: {message_type}")

        if self._task is not None:
            await self._task
            self._task = None
