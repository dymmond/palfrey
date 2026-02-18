"""ASGI message logging middleware."""

from __future__ import annotations

import logging
from typing import Any

from palfrey.logging_config import TRACE_LEVEL
from palfrey.types import ASGIApplication, Message, ReceiveCallable, Scope, SendCallable

_PLACEHOLDER_FORMAT = {
    "body": "<{length} bytes>",
    "bytes": "<{length} bytes>",
    "text": "<{length} chars>",
    "headers": "<...>",
}


def message_with_placeholders(message: dict[str, Any]) -> dict[str, Any]:
    """Return ASGI payload with body-like fields masked for log readability.

    Args:
        message: ASGI scope/event payload.

    Returns:
        Copy of the payload with potentially large fields replaced by length
        placeholders.
    """

    masked = message.copy()
    for field, template in _PLACEHOLDER_FORMAT.items():
        value = message.get(field)
        if value is None:
            continue
        masked[field] = template.format(length=len(value))
    return masked


class MessageLoggerMiddleware:
    """Log ASGI receive/send lifecycle messages at trace level."""

    def __init__(self, app: ASGIApplication, logger_name: str = "palfrey.asgi") -> None:
        """Create message logger middleware.

        Args:
            app: Wrapped ASGI application.
            logger_name: Logger name for emitted messages.
        """

        self.app = app
        self.logger = logging.getLogger(logger_name)
        self._task_counter = 0

    def _trace(self, template: str, *args: Any) -> None:
        self.logger.log(TRACE_LEVEL, template, *args)

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Wrap receive/send callables and log ASGI lifecycle messages."""

        self._task_counter += 1
        task_counter = self._task_counter
        client = scope.get("client")
        if isinstance(client, tuple) and len(client) >= 2:
            prefix = f"{client[0]}:{client[1]} - ASGI"
        else:
            prefix = "ASGI"

        async def wrapped_receive() -> Message:
            message = await receive()
            self._trace(
                "%s [%d] Receive %s", prefix, task_counter, message_with_placeholders(message)
            )
            return message

        async def wrapped_send(message: Message) -> None:
            self._trace("%s [%d] Send %s", prefix, task_counter, message_with_placeholders(message))
            await send(message)

        self._trace(
            "%s [%d] Started scope=%s", prefix, task_counter, message_with_placeholders(scope)
        )
        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except BaseException as exc:  # noqa: BLE001
            self._trace("%s [%d] Raised exception", prefix, task_counter)
            raise exc from None
        else:
            self._trace("%s [%d] Completed", prefix, task_counter)
