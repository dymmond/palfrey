"""Quickstart example for Palfrey."""

from palfrey import run


async def app(scope, receive, send):
    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"hello from palfrey"})


if __name__ == "__main__":
    run(app, host="127.0.0.1", port=8000)
