# WebSockets

Palfrey implements RFC6455 handshake and frame processing for ASGI WebSocket scopes.

## Implemented behavior

- Handshake validation (`Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13`).
- Upgrade response with `Sec-WebSocket-Accept`.
- Client masked-frame enforcement.
- Text/binary frame receive and send support.
- Ping/Pong handling.
- Close frame handling and disconnect propagation.

## Example

```python
{!> ../../../docs_src//protocols/websocket_echo.py !}
```

## Related tests

- `tests/protocols/test_websocket_protocol.py`
- `tests/integration/test_websocket_integration.py`
