from __future__ import annotations


async def app(scope, receive, send):
    """Return scheme/client as seen by the app."""
    if scope["type"] != "http":
        return

    body = f"scheme={scope.get('scheme')} client={scope.get('client')}".encode()
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
