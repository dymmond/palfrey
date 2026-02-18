from __future__ import annotations

from palfrey import run


async def app(scope, receive, send):
    """Simple HTTP responder for programmatic startup demos."""
    if scope["type"] != "http":
        return

    body = b"programmatic run"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", b"16")],
        }
    )
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    run("docs_src.reference.programmatic_run:app", host="127.0.0.1", port=8000)
