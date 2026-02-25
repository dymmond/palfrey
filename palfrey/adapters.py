from __future__ import annotations

import asyncio
import io
import sys
from collections.abc import Iterable
from types import TracebackType
from typing import Any

from palfrey.types import ASGI2Application, ReceiveCallable, Scope, SendCallable


class ASGI2Adapter:
    """
    Adapts an ASGI 2.0 application callable to the ASGI 3.0 asynchronous signature.

    ASGI 2.0 uses a double-callable pattern where the application is called with the
    scope to return a coroutine, which is then called with receive and send. This
    adapter wraps that logic to provide a single `__call__` compatible with ASGI 3.0.
    """

    def __init__(self, app: ASGI2Application) -> None:
        """
        Initializes the adapter with an ASGI 2.0 application.

        Args:
            app (ASGI2Application): The original ASGI 2.0 application callable.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """
        Executes the wrapped ASGI 2.0 application using the provided ASGI 3.0 arguments.

        Args:
            scope (Scope): The connection scope mapping containing request metadata.
            receive (ReceiveCallable): An awaitable callable used to receive messages.
            send (SendCallable): An awaitable callable used to send messages.
        """
        # In ASGI2, the app is called with scope to return an 'instance' coroutine
        instance = self._app(scope)
        # The instance is then awaited with the receive and send callables
        await instance(receive, send)


class WSGIAdapter:
    """
    Provides a bridge to run synchronous WSGI applications within an asynchronous ASGI server.

    This adapter handles the translation of ASGI HTTP scopes into WSGI environments,
    executes the WSGI callable in a separate worker thread to avoid blocking the
    event loop, and pipes the WSGI response back to the ASGI client via an async queue.
    """

    def __init__(self, app: Any) -> None:
        """
        Initializes the adapter with a WSGI application.

        Args:
            app (Any): The synchronous WSGI application callable.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """
        Mediates an ASGI HTTP connection by executing the wrapped WSGI application.

        The process involves accumulating the full request body (as WSGI is synchronous),
        building the WSGI environment, and managing thread-safe communication between
        the WSGI worker thread and the ASGI event loop.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (ReceiveCallable): The ASGI receive channel.
            send (SendCallable): The ASGI send channel.

        Raises:
            RuntimeError: If the scope type is not 'http'.
            BaseException: Re-raises exceptions encountered within the WSGI application.
        """
        if scope["type"] != "http":
            raise RuntimeError("WSGI interface only supports HTTP scopes")

        # WSGI requires a synchronous stream for body; we must buffer the ASGI body first
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        environ = self._build_wsgi_environ(scope, body)
        loop = asyncio.get_running_loop()
        # Queue used to pass dict messages from the WSGI thread back to the main loop
        send_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        response_started = False
        captured_exc_info: (
            tuple[type[BaseException], BaseException, TracebackType | None] | None
        ) = None

        def enqueue(message: dict[str, Any] | None) -> None:
            """Helper to push messages to the async queue from a synchronous thread."""
            loop.call_soon_threadsafe(send_queue.put_nowait, message)

        def start_response(
            status: str,
            headers: list[tuple[str, str]],
            exc_info: (
                tuple[type[BaseException], BaseException, TracebackType | None] | None
            ) = None,
        ) -> None:
            """WSGI start_response callable passed to the application."""
            nonlocal response_started, captured_exc_info
            captured_exc_info = exc_info
            if response_started:
                return

            response_started = True
            # Parse the integer status code from the "200 OK" string
            status_code = int(status.split(" ", 1)[0])
            encoded_headers = [
                (name.encode("latin-1"), value.encode("latin-1")) for name, value in headers
            ]
            enqueue(
                {
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": encoded_headers,
                }
            )

        def run_wsgi() -> None:
            """Core execution logic of the WSGI app within the worker thread."""
            result = self._app(environ, start_response)
            close_result = getattr(result, "close", None)
            try:
                # Iterate over the WSGI iterable and stream chunks as body events
                for chunk in result if isinstance(result, Iterable) else [result]:
                    enqueue({"type": "http.response.body", "body": chunk, "more_body": True})
            finally:
                if callable(close_result):
                    close_result()
            # Send final empty body to signify completion
            enqueue({"type": "http.response.body", "body": b"", "more_body": False})

        def run_wsgi_with_signal() -> None:
            """Wrapper to ensure the queue is closed regardless of success or failure."""
            try:
                run_wsgi()
            finally:
                enqueue(None)

        # Offload the synchronous WSGI execution to a worker thread
        wsgi_task = asyncio.create_task(asyncio.to_thread(run_wsgi_with_signal))
        while True:
            message = await send_queue.get()
            if message is None:
                break
            await send(message)
        await wsgi_task

        # If the WSGI app provided exc_info via start_response, re-raise it here
        if captured_exc_info is not None:
            _, exc_value, traceback = captured_exc_info
            raise exc_value.with_traceback(traceback)

    @staticmethod
    def _build_wsgi_environ(scope: Scope, body: bytes) -> dict[str, Any]:
        """
        Constructs a WSGI environment dictionary from an ASGI scope and body.

        Args:
            scope (Scope): The ASGI scope dictionary.
            body (bytes): The pre-buffered request body.

        Returns:
            dict[str, Any]: A PEP 3333 compliant WSGI environment dictionary.
        """
        script_name = scope.get("root_path", "").encode("utf8").decode("latin1")
        path_info = scope.get("path", "").encode("utf8").decode("latin1")

        # Adjust PATH_INFO if it is prefixed by SCRIPT_NAME (root_path)
        if path_info.startswith(script_name):
            path_info = path_info[len(script_name) :]
        query_string = scope.get("query_string", b"").decode("ascii")

        environ: dict[str, Any] = {
            "REQUEST_METHOD": scope.get("method", "GET"),
            "SCRIPT_NAME": script_name,
            "PATH_INFO": path_info,
            "QUERY_STRING": query_string,
            "SERVER_PROTOCOL": f"HTTP/{scope.get('http_version', '1.1')}",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": scope.get("scheme", "http"),
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stdout,
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }

        client = scope.get("client")
        server = scope.get("server")
        if server is None:
            server = ("localhost", 80)
        environ["SERVER_NAME"] = server[0]
        environ["SERVER_PORT"] = str(server[1]) if server[1] is not None else ""

        if client is not None:
            environ["REMOTE_ADDR"] = client[0]

        # Convert ASGI byte headers into WSGI string environment variables
        for header_name, header_value in scope.get("headers", []):
            name_str = header_name.decode("latin1")
            if name_str == "content-length":
                key = "CONTENT_LENGTH"
            elif name_str == "content-type":
                key = "CONTENT_TYPE"
            else:
                key = "HTTP_" + name_str.upper().replace("-", "_")
            value_str = header_value.decode("latin1")

            # Handle duplicate headers by joining them with commas
            if key in environ:
                existing = environ[key]
                if isinstance(existing, str):
                    value_str = existing + "," + value_str
            environ[key] = value_str

        return environ
