# ASGI Fundamentals

ASGI is the contract between Palfrey and your application.

## The Three Inputs Every ASGI App Receives

- `scope`: metadata about protocol and connection context
- `receive`: async callable yielding inbound messages
- `send`: async callable accepting outbound messages

Minimal app example:

```python
{!> ../../../docs_src/concepts/asgi_minimal.py !}
```

Scope inspector example:

```python
{!> ../../../docs_src/concepts/asgi_scope_inspector.py !}
```

## Scope by Protocol

## HTTP scope

Typical fields:

- `type = "http"`
- `method`
- `path`, `raw_path`, `query_string`
- `headers`
- `client`, `server`

## WebSocket scope

Typical fields:

- `type = "websocket"`
- `subprotocols`
- `extensions`
- shared network/path/header fields

## Lifespan scope

Typical fields:

- `type = "lifespan"`
- app startup/shutdown channel

## Message Sequences

## HTTP

1. app receives one or more `http.request`
2. app sends `http.response.start`
3. app sends one or more `http.response.body`

## WebSocket

1. app receives `websocket.connect`
2. app sends `websocket.accept` or `websocket.close`
3. app and client exchange messages
4. disconnect/close completes session

## Lifespan

1. app receives startup event
2. app initializes shared resources
3. app receives shutdown event
4. app releases resources

## Common ASGI Mistakes

- not sending `http.response.start` before body
- returning non-`None` from ASGI app
- sending websocket messages before `websocket.accept`
- assuming headers are strings instead of bytes

## Why engineers care

ASGI correctness directly affects interoperability and reliability.

## Why non-technical stakeholders should care

A standard contract reduces integration risk and speeds migration between frameworks and runtimes.
