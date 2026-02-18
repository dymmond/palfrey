from palfrey import run


async def app(scope, receive, send):
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            if message["type"] == "websocket.receive":
                await send({"type": "websocket.send", "text": message.get("text", "")})


if __name__ == "__main__":
    run(app, ws="auto")
