from __future__ import annotations

import json


async def app(scope, receive, send):
    """Return protocol metadata useful during debugging."""
    if scope["type"] != "http":
        return

    payload = {
        "type": scope["type"],
        "method": scope.get("method"),
        "path": scope.get("path"),
        "root_path": scope.get("root_path"),
        "client": scope.get("client"),
        "server": scope.get("server"),
        "scheme": scope.get("scheme"),
    }
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
