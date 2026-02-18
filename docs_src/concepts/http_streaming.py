from __future__ import annotations

import asyncio


async def app(scope, receive, send):
    """Send a chunked response with small delays."""
    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )

    for chunk in (b"chunk-1\n", b"chunk-2\n", b"chunk-3\n"):
        await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await asyncio.sleep(0.2)

    await send({"type": "http.response.body", "body": b"", "more_body": False})
