# ASGI Fundamentals

ASGI is the interface between Palfrey and your application.

## The Callable Contract

An ASGI app is an async callable receiving:

- `scope`: connection metadata
- `receive`: async function for inbound messages
- `send`: async function for outbound messages

Minimal example:

```python
{!> ../../../docs_src/concepts/asgi_minimal.py !}
```

## Scope Fields You Use Most

- `scope["type"]`: protocol (`http`, `websocket`, `lifespan`)
- `scope["path"]`: request path
- `scope["query_string"]`: raw query bytes
- `scope["headers"]`: byte header pairs
- `scope["client"]` / `scope["server"]`: endpoint tuples
- `scope["root_path"]`: submount prefix set by server config

Inspect scope example:

```python
{!> ../../../docs_src/concepts/asgi_scope_inspector.py !}
```

## HTTP Message Flow (Conceptual)

1. Palfrey sends `http.request` (possibly in chunks).
2. App sends `http.response.start` once.
3. App sends one or more `http.response.body` messages.

## WebSocket Message Flow (Conceptual)

1. Palfrey raises `websocket.connect` to app.
2. App accepts or closes.
3. Bidirectional `websocket.receive` / `websocket.send` flow.
4. Close handshake ends session.

## Lifespan Message Flow

1. `lifespan.startup`
2. app initialization
3. `lifespan.shutdown`
4. cleanup completion

## Non-Technical Translation

ASGI is like a standard plug shape.
Any compliant server can host any compliant app with the same plug.
That decoupling is what gives teams framework and server flexibility.
