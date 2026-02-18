from __future__ import annotations


async def app(scope, receive, send):
    """Accept websocket clients and echo text messages."""
    if scope["type"] != "websocket":
        return

    await send({"type": "websocket.accept"})
    while True:
        message = await receive()
        message_type = message["type"]

        if message_type == "websocket.disconnect":
            break

        if message_type == "websocket.receive" and "text" in message:
            await send({"type": "websocket.send", "text": message["text"]})
