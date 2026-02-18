from __future__ import annotations

import json
from datetime import datetime, timezone


async def app(scope, receive, send):
    """Return a JSON payload for HTTP requests."""
    if scope["type"] != "http":
        return

    payload = {
        "service": "palfrey-demo",
        "path": scope.get("path", "/"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")

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
