# Custom Protocols and Extensions

Palfrey is designed to be extensible, allowing advanced users to build custom protocols, add middleware, or integrate high-performance acceleration layers. This guide covers the primary extension points and how to use them effectively.

## Protocol Handlers

Palfrey manages the lifecycle of a connection from the initial byte stream to ASGI event dispatch.

### Connection Lifecycle

1.  **Connection**: A client connects via TCP or UNIX socket.
2.  **Parse**: Palfrey reads the initial bytes (the request head) and parses them into a structured format (like `HTTPRequest`).
3.  **Dispatch**: Based on the parsed data, Palfrey constructs an ASGI `scope` and calls the application with `receive` and `send` callables.
4.  **Response**: The application sends events back to Palfrey, which encodes them into wire bytes and writes them to the socket.

### Extending Protocols

While Palfrey supports HTTP/1.1, HTTP/2, HTTP/3, and WebSockets out of the box, you can extend its behavior by wrapping the existing protocol logic or implementing custom handlers if you need to support a completely different protocol.

## Custom Middleware

The most common way to extend Palfrey's behavior is through ASGI middleware. Middleware wraps the application, allowing you to intercept and modify the `scope`, `receive`, and `send` streams.

### Middleware Pattern

A standard ASGI middleware is a class that accepts the next application in the stack and implements an async `__call__` method.

{!> ../../../docs_src/custom-protocols/middleware_example.py !}

## Acceleration Layer

Palfrey uses an acceleration shim pattern to provide high-performance implementations of critical functions using Rust, while maintaining pure Python fallbacks for environments where compiled extensions are unavailable.

### Adding Accelerated Functions

If you are extending Palfrey with custom logic that requires high performance (e.g., custom parsing or cryptographic operations), you can follow the same pattern:

{!> ../../../docs_src/custom-protocols/accel_example.py !}

This pattern ensures that:
*   The server remains functional even if the Rust extension fails to load.
*   Users can opt-out of acceleration using the `PALFREY_NO_RUST` environment variable.
*   The transition between implementations is transparent to the rest of the codebase.

## Using Palfrey as a Library

You can embed Palfrey directly into your application instead of using the CLI. This is useful for building custom server distributions or integrating Palfrey into larger systems.

```python
import asyncio
from palfrey import PalfreyServer, PalfreyConfig

async def app(scope, receive, send):
    # Your ASGI application logic
    ...

async def main():
    config = PalfreyConfig(app="main:app", host="127.0.0.1", port=8000)
    server = PalfreyServer(config=config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing Custom Extensions

When building extensions for Palfrey, we recommend following the same testing patterns used in the Palfrey core.

### Testing Middleware

Use `asyncio` to run your middleware against a mock app and verify the intercepted events.

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_timing_middleware():
    async def mock_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = TimingMiddleware(mock_app)

    # Track headers sent to 'send'
    sent_headers = []
    async def mock_send(message):
        if message["type"] == "http.response.start":
            sent_headers.extend(message.get("headers", []))

    scope = {"type": "http", "method": "GET", "path": "/"}
    await middleware(scope, None, mock_send)

    # Verify the x-process-time header was added
    assert any(name == b"x-process-time" for name, value in sent_headers)
```

### Testing Protocol Logic

For lower-level protocol logic, you can use helpers like `make_stream_reader` (found in Palfrey's test suite) to simulate network input and verify the parsed results.

Refer to `tests/protocols/test_http_asgi.py` for comprehensive examples of how Palfrey tests its own protocol implementations.
