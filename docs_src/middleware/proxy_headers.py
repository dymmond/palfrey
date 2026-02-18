from palfrey import run


async def app(scope, receive, send):
    if scope["type"] == "http":
        client = scope.get("client")
        body = f"client={client}".encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    run(app, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
