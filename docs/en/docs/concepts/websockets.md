# WebSockets

WebSockets turn an HTTP upgrade into a long-lived bidirectional channel.

## Handshake essentials

Client must send valid upgrade headers, including:

- `Upgrade: websocket`
- `Connection: Upgrade`
- `Sec-WebSocket-Key`
- `Sec-WebSocket-Version: 13`

If handshake validation fails, connection is rejected.

## ASGI flow

1. app receives `websocket.connect`
2. app sends one of:
   - `websocket.accept`
   - `websocket.close`
   - `websocket.http.response.start` + body (HTTP-style rejection path)
3. after accept, app handles receive/send messages
4. close handshake and disconnect complete session

Easy echo example:

```python
{!> ../../../docs_src/concepts/websocket_echo.py !}
```

Auth gate example:

```python
{!> ../../../docs_src/concepts/websocket_auth_gate.py !}
```

Stateful room example:

```python
{!> ../../../docs_src/concepts/websocket_chat_room.py !}
```

## Runtime controls

- `--ws`: backend mode selection
- `--ws-max-size`: max frame/message size
- `--ws-max-queue`: receive queue sizing
- `--ws-ping-interval` and `--ws-ping-timeout`
- `--ws-per-message-deflate`

## Failure cases you should test

- invalid handshake headers
- oversized payloads
- invalid UTF-8 text frames
- half-open disconnects
- proxy configurations that drop upgrade headers

## Plain-language explanation

HTTP is a request letter.
WebSocket is a live conversation.
It stays open until one side closes.
