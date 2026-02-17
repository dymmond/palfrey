"""Programmatic config example."""

from palfrey import PalfreyConfig, PalfreyServer


async def app(scope, receive, send):
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"configured"})


config = PalfreyConfig(
    app=app,
    host="127.0.0.1",
    port=9000,
    access_log=True,
    headers=["x-powered-by: palfrey"],
)

server = PalfreyServer(config)

if __name__ == "__main__":
    server.run()
