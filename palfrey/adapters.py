"""ASGI interface adapters.

These adapters mirror Uvicorn interface modes (`asgi3`, `asgi2`, `wsgi`) using
clean-room Palfrey implementations.
"""

from __future__ import annotations

import asyncio
import io
import sys
from collections.abc import Iterable
from types import TracebackType
from typing import Any

from palfrey.types import ASGI2Application, ReceiveCallable, Scope, SendCallable


class ASGI2Adapter:
    """Adapt an ASGI2 callable (`app(scope)(receive, send)`) to ASGI3 style."""

    def __init__(self, app: ASGI2Application) -> None:
        """Store the wrapped ASGI2 callable.

        Args:
            app: ASGI2 application callable.
        """

        self._app = app

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Invoke the wrapped ASGI2 application."""

        instance = self._app(scope)
        await instance(receive, send)


class WSGIAdapter:
    """Adapt a WSGI application to ASGI.

    The adapter executes the WSGI callable in a worker thread and bridges the
    generated response back into ASGI send events.
    """

    def __init__(self, app: Any) -> None:
        """Store the wrapped WSGI app.

        Args:
            app: WSGI application callable.
        """

        self._app = app

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Handle an HTTP request scope via the wrapped WSGI app."""

        if scope["type"] != "http":
            raise RuntimeError("WSGI interface only supports HTTP scopes")

        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        environ = self._build_wsgi_environ(scope, body)
        loop = asyncio.get_running_loop()
        send_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        response_started = False
        captured_exc_info: (
            tuple[type[BaseException], BaseException, TracebackType | None] | None
        ) = None

        def enqueue(message: dict[str, Any] | None) -> None:
            loop.call_soon_threadsafe(send_queue.put_nowait, message)

        def start_response(
            status: str,
            headers: list[tuple[str, str]],
            exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None,
        ) -> None:
            nonlocal response_started, captured_exc_info
            captured_exc_info = exc_info
            if response_started:
                return

            response_started = True
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
            result = self._app(environ, start_response)
            close_result = getattr(result, "close", None)
            try:
                for chunk in result if isinstance(result, Iterable) else [result]:
                    enqueue({"type": "http.response.body", "body": chunk, "more_body": True})
            finally:
                if callable(close_result):
                    close_result()
            enqueue({"type": "http.response.body", "body": b"", "more_body": False})

        def run_wsgi_with_signal() -> None:
            try:
                run_wsgi()
            finally:
                enqueue(None)

        wsgi_task = asyncio.create_task(asyncio.to_thread(run_wsgi_with_signal))
        while True:
            message = await send_queue.get()
            if message is None:
                break
            await send(message)
        await wsgi_task

        if captured_exc_info is not None:
            _, exc_value, traceback = captured_exc_info
            raise exc_value.with_traceback(traceback)

    @staticmethod
    def _build_wsgi_environ(scope: Scope, body: bytes) -> dict[str, Any]:
        """Translate an ASGI scope into a WSGI environ mapping."""

        script_name = scope.get("root_path", "").encode("utf8").decode("latin1")
        path_info = scope.get("path", "").encode("utf8").decode("latin1")
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
        environ["SERVER_PORT"] = server[1]

        if client is not None:
            environ["REMOTE_ADDR"] = client[0]

        for header_name, header_value in scope.get("headers", []):
            name_str = header_name.decode("latin1")
            if name_str == "content-length":
                key = "CONTENT_LENGTH"
            elif name_str == "content-type":
                key = "CONTENT_TYPE"
            else:
                key = "HTTP_" + name_str.upper().replace("-", "_")
            value_str = header_value.decode("latin1")
            if key in environ:
                existing = environ[key]
                if isinstance(existing, str):
                    value_str = existing + "," + value_str
            environ[key] = value_str

        return environ
