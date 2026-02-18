# Middleware

Middleware wraps an ASGI app to add cross-cutting behavior without changing business handlers.

## Common middleware concerns

- request logging
- proxy header normalization
- authentication gates
- timing and tracing

Proxy header wrapper example:

```python
{!> ../../../docs_src/concepts/proxy_headers_middleware.py !}
```

## Ordering guidance

Order matters because each middleware sees transformed scope/messages from previous layers.

Typical pattern:

1. trusted-proxy normalization
2. security/auth controls
3. observability/logging
4. application routing layer

## Non-Technical explanation

If the app is the core service desk, middleware are specialist staff that pre-check IDs, stamp tickets, and log each interaction.

## Practical caution

Do not trust proxy headers from untrusted sources. Always combine middleware usage with explicit trusted IP policy.
