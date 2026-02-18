from __future__ import annotations

from urllib.parse import parse_qs


async def app(scope, receive, send):
    """Allow upgrades only when a known token is present."""
    if scope["type"] != "websocket":
        return

    query_string = scope.get("query_string", b"").decode("utf-8")
    params = parse_qs(query_string)
    token = params.get("token", [""])[0]

    if token != "demo-token":
        await send({"type": "websocket.close", "code": 1008, "reason": "unauthorized"})
        return

    await send({"type": "websocket.accept"})
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            break
        if message["type"] == "websocket.receive" and "text" in message:
            await send({"type": "websocket.send", "text": f"secure:{message['text']}"})
