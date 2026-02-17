# Logging Reference

## Built-in options

- `--log-level`
- `--log-config`
- `--access-log`
- `--use-colors`

## JSON log config example

```python
{!> ../../../docs_src//logging/logging_json.py !}
```

## Message logger middleware

At `--log-level trace`, Palfrey wraps the app with `MessageLoggerMiddleware` and logs ASGI message flow.
