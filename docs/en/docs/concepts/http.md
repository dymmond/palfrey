# HTTP Concepts

This page explains how Palfrey handles incoming HTTP requests and outgoing responses.

## Request Parsing

Palfrey reads request head, parses method/target/version/headers, then reads body by:

- `Content-Length` when present
- chunked decoding when `Transfer-Encoding: chunked`

Example app that reads request body:

```python
{!> ../../../docs_src/concepts/http_read_body.py !}
```

## Streaming Responses

ASGI lets apps send response chunks incrementally.

```python
{!> ../../../docs_src/concepts/http_streaming.py !}
```

## Keep-Alive behavior

Connections may stay open for additional requests when protocol/headers allow.
Keep-alive idle timeout is controlled with:

```bash
palfrey myapp.main:app --timeout-keep-alive 5
```

## Default headers

Palfrey can add default `server` and `date` response headers unless disabled:

```bash
palfrey myapp.main:app --no-server-header --no-date-header
```

## Error paths

- Malformed requests can yield `400 Bad Request`.
- Application exceptions can yield `500 Internal Server Error` if no response is finalized.
- Concurrency limit breaches yield `503 Service Unavailable`.

## Non-Technical explanation

HTTP handling is the front desk workflow:

- read request clearly
- route to application logic
- send a complete and standards-compliant response
- close or reuse connection safely
