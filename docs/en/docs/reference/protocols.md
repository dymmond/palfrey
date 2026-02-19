# Protocols

Palfrey supports ASGI protocol scopes for HTTP, WebSocket, and lifespan.

## HTTP protocol behavior

App message contract:

1. receive `http.request` events
2. send one `http.response.start`
3. send one or more `http.response.body`

Operationally relevant controls:

- `--http`
- `--h11-max-incomplete-event-size`
- `--timeout-keep-alive`
- `--limit-concurrency`

HTTP backend modes:

- `h11`: pure-Python HTTP/1.1 parser
- `httptools`: C-accelerated HTTP/1.1 parser
- `h2`: HTTP/2 stream processing backend
- `h3`: HTTP/3 (QUIC) backend

HTTP/3 notes:

- requires TLS cert+key
- runs over UDP/QUIC instead of TCP
- does not use Unix socket (`--uds`) or inherited FD (`--fd`) modes
- websocket mode is disabled in HTTP/3 runtime mode

## WebSocket protocol behavior

Handshake requirements:

- valid websocket upgrade headers
- valid `Sec-WebSocket-Version: 13`
- valid `Sec-WebSocket-Key`

App message contract:

1. receive `websocket.connect`
2. send `websocket.accept`/`websocket.close`/HTTP rejection extension events
3. exchange `websocket.receive` and `websocket.send`
4. process disconnect/close

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

## Lifespan protocol behavior

Used for startup/shutdown resource management.
See [Lifespan](../concepts/lifespan.md) for lifecycle detail.

## Interface modes

- `auto`
- `asgi3`
- `asgi2`
- `wsgi`

Note:
WSGI mode is HTTP-only and does not provide websocket semantics.

## Protocol testing checklist

- valid and malformed HTTP requests
- keep-alive behavior under load
- websocket handshake accept/reject cases
- websocket text/binary/fragment/control frames
- startup and shutdown lifespan behavior

## Plain-language summary

Protocols define the rules of conversation between clients, server, and app.
When these rules are explicit, behavior becomes predictable.
