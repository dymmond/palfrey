# Protocols Reference

Palfrey operates on ASGI protocol scopes: HTTP, WebSocket, and Lifespan.

## HTTP

Expected app message sequence:

1. receive `http.request`
2. send `http.response.start`
3. send one or more `http.response.body`

Operational controls:

- `--timeout-keep-alive`
- `--limit-concurrency`
- `--h11-max-incomplete-event-size`
- `--server-header` and `--date-header`

## WebSocket

Handshake requirements include valid `Sec-WebSocket-Key` and supported version.
App flow:

1. app receives `websocket.connect`
2. app sends `websocket.accept` or `websocket.close`
3. message exchange with `websocket.receive` / `websocket.send`
4. disconnect handled with close semantics

Example:

```python
{!> ../../../docs_src/protocols/websocket_echo.py !}
```

Controls:

- `--ws`
- `--ws-max-size`
- `--ws-max-queue`
- `--ws-ping-interval`
- `--ws-ping-timeout`
- `--ws-per-message-deflate`

## Lifespan

Lifespan is used for startup/shutdown orchestration.
See [Lifespan Concepts](../concepts/lifespan.md) for lifecycle details.

## Interface modes

Palfrey exposes interface compatibility modes:

- `auto`
- `asgi3`
- `asgi2`
- `wsgi`

WSGI mode does not support WebSocket semantics.

## Operator advice

When introducing a protocol feature, add a targeted smoke check in CI for that exact protocol path.
