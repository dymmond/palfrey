from __future__ import annotations

from collections import defaultdict

ROOMS: dict[str, set] = defaultdict(set)


async def app(scope, receive, send):
    """Broadcast received messages to all clients in one room."""
    if scope["type"] != "websocket":
        return

    query = scope.get("query_string", b"").decode("ascii")
    room = "general"
    if query.startswith("room="):
        room = query.split("=", 1)[1] or "general"

    await send({"type": "websocket.accept", "subprotocol": None})
    ROOMS[room].add(send)

    try:
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                break

            text = message.get("text")
            if text is None:
                continue

            for peer_send in list(ROOMS[room]):
                await peer_send({"type": "websocket.send", "text": f"[{room}] {text}"})
    finally:
        ROOMS[room].discard(send)
