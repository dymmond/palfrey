# Protocols Reference

## HTTP

- Request head parsing with configurable max incomplete-event size (`--h11-max-incomplete-event-size`)
- Body handling via `Content-Length` and chunked transfer encoding
- ASGI response event mapping

## WebSocket

- Handshake validation and upgrade flow
- Text/binary frame handling
- Ping/Pong handling and close semantics

## Lifespan

- startup/shutdown event exchange through `LifespanManager`
