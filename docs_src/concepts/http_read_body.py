from __future__ import annotations


async def read_body(receive):
    """Collect request body chunks into one byte string."""
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        body += message.get("body", b"")
        more_body = message.get("more_body", False)
    return body


async def app(scope, receive, send):
    """Echo request size in plain text."""
    if scope["type"] != "http":
        return

    body = await read_body(receive)
    response = f"Received {len(body)} bytes".encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(response)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": response})
