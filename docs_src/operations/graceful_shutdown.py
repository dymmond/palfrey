from __future__ import annotations

import asyncio


async def app(scope, receive, send):
    """Simulate work and return once complete."""
    if scope["type"] != "http":
        return

    await asyncio.sleep(0.2)
    body = b"finished"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
