from __future__ import annotations

import time

STARTED = time.time()


async def app(scope, receive, send):
    """Expose uptime and status for probe endpoints."""
    if scope["type"] != "http":
        return

    path = scope.get("path", "/")
    if path == "/healthz":
        body = b"ok"
        status = 200
    elif path == "/readyz":
        body = f"uptime={time.time() - STARTED:.2f}".encode()
        status = 200
    else:
        body = b"not found"
        status = 404

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
