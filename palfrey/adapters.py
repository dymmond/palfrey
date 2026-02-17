"""ASGI interface adapters.

These adapters mirror Uvicorn interface modes (`asgi3`, `asgi2`, `wsgi`) using
clean-room Palfrey implementations.
"""

from __future__ import annotations

import asyncio
import io
import sys
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

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
        start_response_state: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
            start_response_state["status"] = status
            start_response_state["headers"] = headers
            return None

        def run_wsgi() -> tuple[str, list[tuple[str, str]], bytes]:
            result = self._app(environ, start_response)
            payload = b"".join(result if isinstance(result, Iterable) else [result])
            status = start_response_state.get("status", "500 Internal Server Error")
            headers = start_response_state.get("headers", [])
            return status, headers, payload

        status_line, headers, payload = await asyncio.to_thread(run_wsgi)
        status_code = int(status_line.split(" ", 1)[0])

        encoded_headers = [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in headers
        ]

        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": encoded_headers,
        })
        await send({"type": "http.response.body", "body": payload, "more_body": False})

    @staticmethod
    def _build_wsgi_environ(scope: Scope, body: bytes) -> dict[str, Any]:
        """Translate an ASGI scope into a WSGI environ mapping."""

        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode("latin-1")

        environ: dict[str, Any] = {
            "REQUEST_METHOD": scope.get("method", "GET"),
            "SCRIPT_NAME": scope.get("root_path", ""),
            "PATH_INFO": quote(path),
            "QUERY_STRING": query_string,
            "SERVER_PROTOCOL": f"HTTP/{scope.get('http_version', '1.1')}",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": scope.get("scheme", "http"),
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        client = scope.get("client")
        server = scope.get("server")
        if client:
            environ["REMOTE_ADDR"] = client[0]
            environ["REMOTE_PORT"] = str(client[1])
        if server:
            environ["SERVER_NAME"] = server[0]
            environ["SERVER_PORT"] = str(server[1])

        for header_name, header_value in scope.get("headers", []):
            key = "HTTP_" + header_name.decode("latin-1").upper().replace("-", "_")
            environ[key] = header_value.decode("latin-1")

        environ["CONTENT_LENGTH"] = str(len(body))
        environ.setdefault("CONTENT_TYPE", "")
        return environ
