"""Benchmark ASGI application targets."""

from __future__ import annotations


async def app(scope, receive, send):
    """Serve HTTP and WebSocket echo paths for benchmark workloads."""

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
        await send({"type": "http.response.body", "body": b"pong"})
        return

    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            if message["type"] == "websocket.receive":
                if "text" in message:
                    await send({"type": "websocket.send", "text": message["text"]})
                else:
                    await send({"type": "websocket.send", "bytes": message.get("bytes", b"")})
