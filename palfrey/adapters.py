from __future__ import annotations

import asyncio
import sys
import tempfile
from collections.abc import Callable, Iterable
from types import TracebackType
from typing import IO, Any

from palfrey.types import ASGI2Application, ReceiveCallable, Scope, SendCallable


class ASGI2Adapter:
    """
    Adapts an ASGI 2.0 application callable to the ASGI 3.0 asynchronous signature.

    ASGI 2.0 relies on a double-callable pattern where the application is first called
    with the connection `scope` to return an instance coroutine, which is then awaited
    with `receive` and `send` channels. This adapter wraps that legacy logic to expose
    a single, ASGI 3.0 compliant `__call__` signature.
    """

    def __init__(self, app: ASGI2Application) -> None:
        """
        Initializes the ASGI 2.0 adapter.

        Args:
            app (ASGI2Application): The original ASGI 2.0 application callable.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """
        Executes the wrapped ASGI 2.0 application using the ASGI 3.0 arguments.

        Args:
            scope (Scope): The ASGI connection scope mapping containing request metadata.
            receive (ReceiveCallable): An awaitable callable used to receive ASGI messages.
            send (SendCallable): An awaitable callable used to send ASGI messages.
        """
        # In ASGI 2.0, the app is called with the scope to return an 'instance' coroutine
        instance = self._app(scope)
        # The instance is then awaited with the receive and send callables
        await instance(receive, send)


class WSGIAdapter:
    """
    Provides a PEP 3333 compliant bridge to run synchronous WSGI applications
    within an asynchronous ASGI server.

    This adapter manages the impedance mismatch between ASGI's async streaming model
    and WSGI's synchronous blocking model. It buffers incoming request bodies using a
    memory-to-disk spool, translates the ASGI HTTP scope into a WSGI environment,
    and offloads the WSGI application execution to a background worker thread to
    prevent event loop blocking.
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

        Args:
            scope (Scope): The ASGI connection scope.
            receive (ReceiveCallable): The ASGI receive channel.
            send (SendCallable): The ASGI send channel.

        Raises:
            RuntimeError: If the ASGI scope type is not 'http'.
            BaseException: Re-raises any exception encountered within the WSGI application.
        """
        if scope["type"] != "http":
            raise RuntimeError("WSGI interface only supports HTTP scopes")

        # Spool to memory up to 1MB, then automatically spill to disk to prevent OOM
        body_file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)

        try:
            # Buffer the ASGI body into the spooled file
            while True:
                message = await receive()
                chunk = message.get("body", b"")
                if chunk:
                    body_file.write(chunk)
                if not message.get("more_body", False):
                    break

            # Reset file pointer to the beginning so the WSGI app can read it
            body_file.seek(0)

            environ = self._build_wsgi_environ(scope, body_file)
            loop = asyncio.get_running_loop()
            send_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            response_started = False
            captured_exc_info: (
                tuple[type[BaseException], BaseException, TracebackType | None] | None
            ) = None

            def enqueue(message: dict[str, Any] | None) -> None:
                """
                Safely pushes messages from the synchronous WSGI thread to the async event loop queue.

                Args:
                    message (dict[str, Any] | None): The ASGI message dictionary, or None to signal completion.
                """
                loop.call_soon_threadsafe(send_queue.put_nowait, message)

            def start_response(
                status: str,
                headers: list[tuple[str, str]],
                exc_info: (
                    tuple[type[BaseException], BaseException, TracebackType | None] | None
                ) = None,
            ) -> Callable[[bytes], None]:
                """
                The PEP 3333 standard callback passed to the WSGI application to start the HTTP response.

                Args:
                    status (str): The HTTP status string (e.g., '200 OK').
                    headers (list[tuple[str, str]]): A list of (header_name, header_value) tuples.
                    exc_info (tuple | None, optional): Exception information provided by the application.

                Returns:
                    Callable[[bytes], None]: A `write(chunk)` callable for unbuffered response streaming.

                Raises:
                    BaseException: Re-raises `exc_info` if headers have already been sent to the client.
                """
                nonlocal response_started, captured_exc_info

                if exc_info is not None:
                    if response_started:
                        # PEP 3333 requires re-raising if headers are already committed
                        raise exc_info[1].with_traceback(exc_info[2])

                captured_exc_info = exc_info

                if not response_started:
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

                def write(chunk: bytes) -> None:
                    """
                    Fallback callable for WSGI applications that push data directly instead of yielding.

                    Args:
                        chunk (bytes): A byte string of response body data.
                    """
                    if chunk:
                        enqueue({"type": "http.response.body", "body": chunk, "more_body": True})

                return write

            def run_wsgi() -> None:
                """
                The core execution logic that runs the synchronous WSGI application.
                Iterates over the application's response and enqueues body chunks.
                """
                result = self._app(environ, start_response)
                close_result = getattr(result, "close", None)
                try:
                    for chunk in result if isinstance(result, Iterable) else [result]:
                        if chunk:
                            enqueue(
                                {"type": "http.response.body", "body": chunk, "more_body": True}
                            )
                finally:
                    if callable(close_result):
                        close_result()
                # Send the final empty body chunk to signify completion
                enqueue({"type": "http.response.body", "body": b"", "more_body": False})

            def run_wsgi_with_signal() -> None:
                """
                Wraps the WSGI execution to ensure the async queue is unblocked via a None
                sentinel when the thread completes, regardless of success or failure.
                """
                try:
                    run_wsgi()
                finally:
                    enqueue(None)

            # Offload synchronous execution to an asyncio worker thread
            wsgi_task = asyncio.create_task(asyncio.to_thread(run_wsgi_with_signal))

            # Async consumer loop: await messages from the queue and send them to the ASGI client
            while True:
                message = await send_queue.get()
                if message is None:
                    break
                await send(message)

            await wsgi_task

            # If the WSGI app yielded an exception via start_response, re-raise it here in the main loop
            if captured_exc_info is not None:
                _, exc_value, traceback = captured_exc_info
                raise exc_value.with_traceback(traceback)

        finally:
            # Ensure the spooled file (and any potential disk-backed temp file) is securely cleaned up
            body_file.close()

    @staticmethod
    def _build_wsgi_environ(scope: Scope, body_file: IO[bytes]) -> dict[str, Any]:
        """
        Constructs a PEP 3333 compliant WSGI environment dictionary from an ASGI scope.

        Handles the strict encoding requirements of PEP 3333, mapping ASGI header
        bytes to latin-1 strings and correctly formatting standard CGI variables.

        Args:
            scope (Scope): The ASGI connection scope.
            body_file (IO[bytes]): The pre-buffered spooled temporary file containing the request body.

        Returns:
            dict[str, Any]: A fully populated WSGI environment dictionary.
        """
        script_name = scope.get("root_path", "").encode("utf8").decode("latin1")
        path_info = scope.get("path", "").encode("utf8").decode("latin1")

        # Adjust PATH_INFO if it is prefixed by SCRIPT_NAME (root_path)
        if script_name and path_info.startswith(script_name):
            path_info = path_info[len(script_name) :]

        query_string = scope.get("query_string", b"").decode("latin1")

        environ: dict[str, Any] = {
            "REQUEST_METHOD": scope.get("method", "GET"),
            "SCRIPT_NAME": script_name,
            "PATH_INFO": path_info,
            "QUERY_STRING": query_string,
            "SERVER_PROTOCOL": f"HTTP/{scope.get('http_version', '1.1')}",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": scope.get("scheme", "http"),
            "wsgi.input": body_file,
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }

        server = scope.get("server") or ("localhost", 80)
        environ["SERVER_NAME"] = server[0]
        environ["SERVER_PORT"] = str(server[1]) if server[1] is not None else "80"

        client = scope.get("client")
        if client is not None:
            environ["REMOTE_ADDR"] = client[0]
        else:
            environ["REMOTE_ADDR"] = "127.0.0.1"

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

            # Handle duplicate headers by joining them with commas per RFC 7230
            if key in environ:
                environ[key] = f"{environ[key]},{value_str}"
            else:
                environ[key] = value_str

        return environ
