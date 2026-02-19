# HTTP

This page explains how Palfrey handles HTTP requests and responses.

## Request lifecycle

1. read and parse request head (`method`, `target`, `version`, headers)
2. read body via `Content-Length` or chunked transfer
3. build HTTP ASGI scope
4. run app receive/send flow
5. serialize and write response

Body-reading example:

```python
{!> ../../../docs_src/concepts/http_read_body.py !}
```

Streaming response example:

```python
{!> ../../../docs_src/concepts/http_streaming.py !}
```

## Response behavior highlights

- `Content-Length` is respected and validated
- chunked responses are supported
- keep-alive is decided from request/response semantics
- configurable default headers (`server`, `date`)

## Request safety controls

- head/body size limits
- optional concurrency limits
- keep-alive timeout
- backlog and graceful shutdown controls

## Important edge cases

## `Expect: 100-continue`

Palfrey supports the `100 Continue` flow before body consumption.

## HEAD requests

Headers are returned while body payload is suppressed.

## Malformed requests

Palfrey returns protocol-appropriate error responses (for example `400`).

## Non-technical explanation

HTTP handling is a disciplined workflow:

- read request clearly
- process with app logic
- send a standards-compliant reply
- keep or close the connection safely
