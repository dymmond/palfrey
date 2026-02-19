from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from palfrey.logging_config import get_logger
from palfrey.types import ASGIApplication, Message, Scope

# Initialize specialized logger for lifespan events
logger = get_logger("palfrey.lifespan")

# Error message constant for protocol violations
STATE_TRANSITION_ERROR = "Got invalid state transition on lifespan protocol."


@dataclass(slots=True)
class LifespanManager:
    """
    Coordinates the ASGI lifespan protocol to manage application startup and shutdown.

    This manager encapsulates the logic for broadcasting 'lifespan.startup' and
    'lifespan.shutdown' events to an ASGI application. It maintains an internal state
    dictionary that can be shared across the application and monitors for protocol
    violations or application-level failures during these critical phases.
    """

    app: ASGIApplication
    lifespan_mode: str = "auto"
    should_exit: bool = False
    state: dict[str, Any] = field(default_factory=dict)

    # Internal communication primitives for the lifespan task
    _receive_queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    _startup_event: asyncio.Event = field(default_factory=asyncio.Event)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None

    # Track failure states to inform the server runtime
    _error_occurred: bool = False
    _startup_failed: bool = False
    _shutdown_failed: bool = False

    async def _receive(self) -> Message:
        """
        ASGI receive callable for the lifespan scope.

        Returns:
            Message: The next lifespan event (startup or shutdown) from the manager.
        """
        return await self._receive_queue.get()

    async def _send(self, message: Message) -> None:
        """
        ASGI send callable for the lifespan scope.

        Handles 'complete' and 'failed' signals from the application and updates
        the manager's internal event synchronization objects.

        Args:
            message (Message): The message sent by the application.

        Raises:
            RuntimeError: If the application sends an event out of order or an
                unrecognized message type.
        """
        message_type = str(message.get("type", ""))

        if message_type == "lifespan.startup.complete":
            # Startup can only complete if we aren't already started or shutting down
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
            # Shutdown can only complete after a successful startup
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
        """
        Internal task runner that executes the application's lifespan callable.

        This method prepares the 'lifespan' scope and handles exceptions. If 'auto' mode
        is enabled, it gracefully downgrades on failures; otherwise, it logs errors.
        """
        scope: Scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "state": self.state,
        }
        try:
            await self.app(scope, self._receive, self._send)
        except BaseException as exc:
            self._error_occurred = True
            # If the app explicitly failed via message, don't log the re-raised exception
            if self._startup_failed or self._shutdown_failed:
                return

            if self.lifespan_mode == "auto":
                logger.info("ASGI 'lifespan' protocol appears unsupported.")
            else:
                logger.error("Exception in 'lifespan' protocol", exc_info=exc)
        finally:
            # Ensure the server doesn't hang if the lifespan task exits unexpectedly
            self._startup_event.set()
            self._shutdown_event.set()

    async def startup(self) -> None:
        """
        Initiates the application startup sequence and waits for completion.

        Signals the application to start by putting a 'lifespan.startup' message
        into the receive queue and waits for the application to acknowledge.

        Raises:
            RuntimeError: If the application startup fails and the manager is in
                a strict lifespan mode.
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
        """
        Initiates the application shutdown sequence and waits for completion.

        Signals the application to shut down by putting a 'lifespan.shutdown' message
        into the receive queue and ensures the lifespan task is cleaned up.
        """
        if self._task is None:
            return

        # If an error occurred during startup/runtime, we might not be able to shut down
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

        # Ensure the background task is fully joined
        await self._task
        self._task = None
