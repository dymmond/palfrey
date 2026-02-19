# Middleware

Middleware wraps an ASGI app to apply shared behavior.

## Typical middleware responsibilities

- auth and access policies
- proxy header normalization
- request/response logging
- timing and tracing
- request IDs or correlation IDs

Proxy header middleware example:

```python
{!> ../../../docs_src/concepts/proxy_headers_middleware.py !}
```

## Ordering matters

A practical order is:

1. trust-boundary middleware (proxy/IP normalization)
2. security middleware (auth/authorization)
3. observability middleware (logging/tracing)
4. application routing/handlers

## Risks to avoid

- trusting forwarded headers from untrusted peers
- logging sensitive payloads by default
- putting expensive work in always-on middleware paths

## Plain-language explanation

If the app is the main service desk, middleware are specialist desks that perform checks before and after each request.
