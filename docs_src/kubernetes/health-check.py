async def app(scope, receive, send):
    """
    Simple ASGI app providing health check endpoints.
    In a real app, this logic would be part of your main application.
    """
    if scope["type"] != "http":
        return

    path = scope["path"]

    if path == "/healthz":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"OK",
            }
        )
    else:
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"Not Found",
            }
        )
