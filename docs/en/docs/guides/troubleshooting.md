# Guide: Troubleshooting

This cookbook focuses on high-frequency production and migration issues.

## 1. Import errors (`Unable to import module ...`)

Symptoms:

- startup fails with import-module error

Checks:

1. Confirm working directory and Python path.
2. Ensure `module:attribute` target is correct.
3. Use `--app-dir` when source tree root is not current working directory.
4. Validate virtual environment activation and installed dependencies.

## 2. Reload not picking up changes

Checks:

- `--reload` enabled
- correct `--reload-dir`
- include/exclude patterns are not over-filtering

## 3. Worker mode boot failures

Checks:

- ensure app target is import string
- verify environment variables available to child processes
- verify file permissions for runtime artifacts (sockets, certs, etc.)

## 4. Proxy client IP/scheme incorrect

Checks:

- `--proxy-headers` enabled
- `--forwarded-allow-ips` includes actual proxy source
- edge proxy forwards expected headers

## 5. WebSocket handshake failures

Checks:

- required upgrade headers present
- reverse proxy supports upgrade forwarding
- app accepts connection and does not close immediately

## 6. Healthcheck reference app

```python
{!> ../../../docs_src/guides/troubleshooting_healthcheck.py !}
```

## Incident capture checklist

- Startup command used.
- Palfrey version and Python version.
- Relevant logs around failure timestamp.
- Reproduction command with exact endpoint and payload.
