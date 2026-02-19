from __future__ import annotations

import logging
from typing import Any

from palfrey.logging_config import TRACE_LEVEL
from palfrey.types import ASGIApplication, Message, ReceiveCallable, Scope, SendCallable

# Map defining how potentially large or sensitive ASGI fields should be masked in logs.
# This ensures that binary bodies or long header lists don't flood the terminal output.
_PLACEHOLDER_FORMAT = {
    "body": "<{length} bytes>",
    "bytes": "<{length} bytes>",
    "text": "<{length} chars>",
    "headers": "<...>",
}


def message_with_placeholders(message: dict[str, Any]) -> dict[str, Any]:
    """
    Generate a sanitized copy of an ASGI message for logging purposes.

    This function iterates through standard ASGI message keys (like 'body', 'headers',
    or 'text') and replaces their actual content with a descriptive placeholder
    indicating the data's size or presence. This prevents massive binary blobs
    from being written to the logs while still providing context.

    Args:
        message (dict[str, Any]): The raw ASGI scope or event dictionary.

    Returns:
        dict[str, Any]: A shallow copy of the message with large fields masked.
    """

    masked = message.copy()
    for field, template in _PLACEHOLDER_FORMAT.items():
        value = message.get(field)
        if value is None:
            continue
        # Format the placeholder string with the actual length of the data.
        masked[field] = template.format(length=len(value))
    return masked


class MessageLoggerMiddleware:
    """
    ASGI middleware that provides low-level trace logging for all incoming and outgoing messages.

    This middleware intercepts the 'receive' and 'send' channels between the server and
    the application. Every event (e.g., http.request, http.response.start) is logged at
    the TRACE level, providing a granular view of the protocol execution. It is
    particularly useful for debugging protocol-level issues or custom ASGI implementations.

    Attributes:
        app (ASGIApplication): The next ASGI application or middleware in the stack.
        logger (logging.Logger): The logger instance used for emitting trace messages.
    """

    def __init__(self, app: ASGIApplication, logger_name: str = "palfrey.asgi") -> None:
        """
        Initialize the logger middleware.

        Args:
            app (ASGIApplication): The wrapped ASGI application.
            logger_name (str): The name for the logger. Defaults to "palfrey.asgi".
        """

        self.app = app
        self.logger = logging.getLogger(logger_name)
        # Internal counter to correlate receive/send events within a single task/request.
        self._task_counter = 0

    def _trace(self, template: str, *args: Any) -> None:
        """
        Helper method to emit logs at the custom TRACE level.
        """
        self.logger.log(TRACE_LEVEL, template, *args)

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """
        The main middleware entry point.

        Wraps the 'receive' and 'send' callables to intercept and log messages. It
        calculates a prefix based on the client address and assigns a unique task
        ID to the current scope.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (ReceiveCallable): The async callable to receive ASGI messages.
            send (SendCallable): The async callable to send ASGI messages.
        """

        self._task_counter += 1
        task_counter = self._task_counter
        client = scope.get("client")

        # Format the log prefix to include client IP:Port if available.
        if isinstance(client, tuple) and len(client) >= 2:
            prefix = f"{client[0]}:{client[1]} - ASGI"
        else:
            prefix = "ASGI"

        async def wrapped_receive() -> Message:
            """
            Intercepts and logs messages coming from the server to the application.
            """
            message = await receive()
            self._trace(
                "%s [%d] Receive %s",
                prefix,
                task_counter,
                message_with_placeholders(message),
            )
            return message

        async def wrapped_send(message: Message) -> None:
            """
            Intercepts and logs messages going from the application back to the server.
            """
            self._trace(
                "%s [%d] Send %s",
                prefix,
                task_counter,
                message_with_placeholders(message),
            )
            await send(message)

        # Log the initial connection scope before calling the application.
        self._trace(
            "%s [%d] Started scope=%s",
            prefix,
            task_counter,
            message_with_placeholders(scope),
        )

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except BaseException as exc:
            # Capture any exception raised by the application stack and log it.
            self._trace("%s [%d] Raised exception", prefix, task_counter)
            raise exc from None
        else:
            # Signal the successful completion of the ASGI task.
            self._trace("%s [%d] Completed", prefix, task_counter)
