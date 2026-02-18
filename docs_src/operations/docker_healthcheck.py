from __future__ import annotations

import time

STARTED_AT = time.time()


async def app(scope, receive, send):
    """Serve liveness and readiness endpoints."""
    if scope["type"] != "http":
        return

    path = scope.get("path", "/")
    if path == "/healthz":
        status = 200
        body = b"ok"
    elif path == "/readyz":
        status = 200
        body = f"ready uptime={time.time() - STARTED_AT:.2f}".encode()
    else:
        status = 404
        body = b"not found"

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
