"""ASGI applications used by integration tests."""

from __future__ import annotations


async def http_app(scope, receive, send):
    """Return a simple HTTP response and lifecycle events."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


async def websocket_app(scope, receive, send):
    """Echo websocket messages."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            if message["type"] == "websocket.receive":
                await send({"type": "websocket.send", "text": message.get("text", "")})


async def websocket_close_app(scope, receive, send):
    """Accept a websocket and immediately close with explicit code/reason."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1001, "reason": "custom reason"})


async def websocket_http_response_app(scope, receive, send):
    """Reject websocket upgrade with HTTP response extension messages."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "websocket":
        await send(
            {
                "type": "websocket.http.response.start",
                "status": 418,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"teapot"})


async def websocket_subprotocol_app(scope, receive, send):
    """Accept websocket and negotiate a known subprotocol when requested."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "websocket":
        chosen = "chat" if "chat" in scope.get("subprotocols", []) else None
        await send({"type": "websocket.accept", "subprotocol": chosen})
        await send({"type": "websocket.close", "code": 1000})


async def http_content_length_app(scope, receive, send):
    """HTTP app that responds with explicit Content-Length framing."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", b"2"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


async def http_head_behavior_app(scope, receive, send):
    """HTTP app used to compare HEAD response behavior to Uvicorn."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", b"4"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"body"})


async def http_multi_set_cookie_app(scope, receive, send):
    """HTTP app returning repeated Set-Cookie headers for parity checks."""

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"set-cookie", b"a=1; Path=/"),
                    (b"set-cookie", b"b=2; Path=/"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


async def lifespan_fail_app(scope, receive, send):
    """Fail lifespan startup to validate process-exit behavior."""

    if scope["type"] != "lifespan":
        return

    message = await receive()
    if message["type"] == "lifespan.startup":
        await send({"type": "lifespan.startup.failed", "message": "startup failed"})
