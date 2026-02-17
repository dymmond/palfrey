# Protocols

## HTTP

Palfrey supports HTTP/1.1 request parsing, request-body handling via `Content-Length`, and ASGI HTTP scope execution.

## WebSocket

Palfrey supports RFC6455 handshake and frame processing for text/binary messaging, close handling, and ping/pong.

## Lifespan

Palfrey supports ASGI lifespan startup/shutdown events (`auto`, `on`, `off`).

## Interface modes

- `asgi3`
- `asgi2` (adapter)
- `wsgi` (adapter)
