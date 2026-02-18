# WebSockets Concepts

WebSockets upgrade an HTTP connection into a long-lived bidirectional channel.

## Handshake Overview

Client sends upgrade headers (`Upgrade`, `Connection`, `Sec-WebSocket-*`).
Palfrey validates handshake and then exposes ASGI websocket events.

## Application acceptance model

- App can accept (`websocket.accept`) and exchange messages.
- App can close (`websocket.close`) to reject or terminate.

Basic echo example:

```python
{!> ../../../docs_src/concepts/websocket_echo.py !}
```

Authenticated gate example:

```python
{!> ../../../docs_src/concepts/websocket_auth_gate.py !}
```

Room fanout example:

```python
{!> ../../../docs_src/concepts/websocket_chat_room.py !}
```

## Operational controls

- `--ws none` to disable WebSocket upgrades.
- `--ws-max-size` to cap frame payload size.
- Ping-related flags are available for compatibility-focused configurations.

## Failure modes to test

- Invalid handshake headers.
- Oversized frames.
- abrupt client disconnects.
- invalid UTF-8 text frames.

## Non-Technical explanation

HTTP is like sending letters.
WebSockets are like opening a phone call and talking both ways until one side hangs up.
