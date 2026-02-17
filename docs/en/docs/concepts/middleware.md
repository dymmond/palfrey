# Middleware

Palfrey includes middleware primitives aligned with Uvicorn ecosystem expectations.

## Proxy headers middleware

`ProxyHeadersMiddleware` adjusts `scope["client"]` and `scope["scheme"]` from trusted `X-Forwarded-*` headers.

```python
{!> ../../../docs_src//middleware/proxy_headers.py !}
```

## Message logger middleware

`MessageLoggerMiddleware` logs ASGI receive/send events (with payload size placeholders) for deep protocol debugging.

## Source mapping

- Uvicorn source: `uvicorn/middleware/proxy_headers.py`
- Uvicorn source: `uvicorn/middleware/message_logger.py`
