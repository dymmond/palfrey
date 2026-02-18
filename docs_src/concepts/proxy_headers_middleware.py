from __future__ import annotations

from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware


async def app(scope, receive, send):
    """Show the client tuple after trusted proxy processing."""
    if scope["type"] != "http":
        return

    client = scope.get("client")
    body = f"client={client}".encode()
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


wrapped_app = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
