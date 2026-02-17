"""ASGI message logging middleware."""

from __future__ import annotations

import logging
from copy import copy

from palfrey.types import ASGIApplication, Message, ReceiveCallable, Scope, SendCallable


class MessageLoggerMiddleware:
    """Log ASGI receive/send events at trace-level equivalent (DEBUG)."""

    def __init__(self, app: ASGIApplication, logger_name: str = "palfrey.asgi") -> None:
        """Create message logger middleware.

        Args:
            app: Wrapped ASGI application.
            logger_name: Logger name for emitted messages.
        """

        self.app = app
        self.logger = logging.getLogger(logger_name)

    def _message_with_placeholders(self, message: Message) -> Message:
        """Mask body payloads to avoid large binary log output."""

        masked = copy(message)
        if "body" in masked:
            masked["body"] = f"<{len(masked['body'])} bytes>"
        if "bytes" in masked:
            masked["bytes"] = f"<{len(masked['bytes'])} bytes>"
        return masked

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Wrap receive/send callables and log their messages."""

        async def wrapped_receive() -> Message:
            message = await receive()
            self.logger.debug("ASGI receive: %s", self._message_with_placeholders(message))
            return message

        async def wrapped_send(message: Message) -> None:
            self.logger.debug("ASGI send: %s", self._message_with_placeholders(message))
            await send(message)

        await self.app(scope, wrapped_receive, wrapped_send)
