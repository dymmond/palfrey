from __future__ import annotations


async def _app(scope, receive, send):
    if scope["type"] != "http":
        return

    body = b"Factory app booted"
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


def create_app():
    """Return the ASGI app instance."""
    return _app
