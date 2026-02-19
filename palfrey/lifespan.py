"""ASGI lifespan protocol support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from palfrey.logging_config import get_logger
from palfrey.types import ASGIApplication, Message, Scope

logger = get_logger("palfrey.lifespan")

STATE_TRANSITION_ERROR = "Got invalid state transition on lifespan protocol."


@dataclass(slots=True)
class LifespanManager:
    """Coordinate ASGI lifespan startup and shutdown events.

    The manager runs the lifespan scope in a dedicated task and exchanges events
    through asyncio queues.
    """

    app: ASGIApplication
    lifespan_mode: str = "auto"
    should_exit: bool = False
    state: dict[str, Any] = field(default_factory=dict)
    _receive_queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    _startup_event: asyncio.Event = field(default_factory=asyncio.Event)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None
    _error_occurred: bool = False
    _startup_failed: bool = False
    _shutdown_failed: bool = False

    async def _receive(self) -> Message:
        return await self._receive_queue.get()

    async def _send(self, message: Message) -> None:
        message_type = str(message.get("type", ""))
        if message_type == "lifespan.startup.complete":
            if self._startup_event.is_set() or self._shutdown_event.is_set():
                raise RuntimeError(STATE_TRANSITION_ERROR)
            self._startup_event.set()
            return

        if message_type == "lifespan.startup.failed":
            if self._startup_event.is_set() or self._shutdown_event.is_set():
                raise RuntimeError(STATE_TRANSITION_ERROR)
            self._startup_failed = True
            self._startup_event.set()
            startup_message = message.get("message")
            if startup_message:
                logger.error("%s", startup_message)
            return

        if message_type == "lifespan.shutdown.complete":
            if not self._startup_event.is_set() or self._shutdown_event.is_set():
                raise RuntimeError(STATE_TRANSITION_ERROR)
            self._shutdown_event.set()
            return

        if message_type == "lifespan.shutdown.failed":
            if not self._startup_event.is_set() or self._shutdown_event.is_set():
                raise RuntimeError(STATE_TRANSITION_ERROR)
            self._shutdown_failed = True
            self._shutdown_event.set()
            shutdown_message = message.get("message")
            if shutdown_message:
                logger.error("%s", shutdown_message)
            return

        raise RuntimeError(f"Unexpected lifespan message: {message_type}")

    async def _run_lifespan(self) -> None:
        scope: Scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "state": self.state,
        }
        try:
            await self.app(scope, self._receive, self._send)
        except BaseException as exc:  # noqa: BLE001
            self._error_occurred = True
            if self._startup_failed or self._shutdown_failed:
                return
            if self.lifespan_mode == "auto":
                logger.info("ASGI 'lifespan' protocol appears unsupported.")
            else:
                logger.error("Exception in 'lifespan' protocol", exc_info=exc)
        finally:
            self._startup_event.set()
            self._shutdown_event.set()

    async def startup(self) -> None:
        """Trigger and await application startup completion.

        Raises:
            RuntimeError: If startup fails.
        """

        if self._task is None:
            self._task = asyncio.create_task(self._run_lifespan())

        logger.info("Waiting for application startup.")
        await self._receive_queue.put({"type": "lifespan.startup"})
        await self._startup_event.wait()

        if self._startup_failed or (self._error_occurred and self.lifespan_mode == "on"):
            logger.error("Application startup failed. Exiting.")
            self.should_exit = True
            return
        logger.info("Application startup complete.")

    async def shutdown(self) -> None:
        """Trigger and await application shutdown completion."""

        if self._task is None:
            return

        if self._error_occurred:
            await self._task
            self._task = None
            return

        logger.info("Waiting for application shutdown.")
        await self._receive_queue.put({"type": "lifespan.shutdown"})
        await self._shutdown_event.wait()

        if self._shutdown_failed or (self._error_occurred and self.lifespan_mode == "on"):
            logger.error("Application shutdown failed. Exiting.")
            self.should_exit = True
        else:
            logger.info("Application shutdown complete.")

        await self._task
        self._task = None
