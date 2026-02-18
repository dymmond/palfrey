from __future__ import annotations


async def app(scope, receive, send):
    """Simple app for systemd deployment snippets."""
    if scope["type"] != "http":
        return

    body = b"systemd-ready"
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
