import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palfrey.types import ASGIApplication, ReceiveCallable, Scope, SendCallable


class TimingMiddleware:
    """
    Example middleware that logs the time taken to process a request.

    This demonstrates the standard ASGI middleware pattern:
    1. Intercept the scope (optional)
    2. Wrap the 'send' callable to intercept response events
    3. Call the next application in the stack
    """

    def __init__(self, app: "ASGIApplication") -> None:
        self.app = app

    async def __call__(
        self, scope: "Scope", receive: "ReceiveCallable", send: "SendCallable"
    ) -> None:
        # We only care about HTTP requests for this example
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                # Calculate duration when the response starts
                duration = time.perf_counter() - start_time
                # Add a custom header with the duration
                headers = list(message.get("headers", []))
                headers.append((b"x-process-time", str(duration).encode("ascii")))
                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, wrapped_send)
