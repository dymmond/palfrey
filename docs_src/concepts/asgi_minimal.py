from __future__ import annotations


async def app(scope, receive, send):
    """Serve HTTP and reject unknown protocols."""
    if scope["type"] != "http":
        raise RuntimeError(f"Unsupported scope type: {scope['type']}")

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": b"ASGI app is running"})
