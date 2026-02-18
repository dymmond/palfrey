from __future__ import annotations


async def app(scope, receive, send):
    """Return a plain-text greeting for HTTP requests."""
    if scope["type"] != "http":
        return

    body = b"Hello from Palfrey"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
