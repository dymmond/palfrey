# CLI Reference

Palfrey CLI is implemented with Click and uses an environment prefix of `PALFREY`.

## Command Shape

```bash
palfrey [OPTIONS] APP
```

- `APP` is typically `module:attribute`.
- Use `--factory` when APP points to a factory function returning an ASGI app.

Example command set:

```python
{!> ../../../docs_src/cli/basic_commands.py !}
```

## Configuration Precedence

Highest to lowest:

1. CLI flags
2. Programmatic config arguments
3. `PALFREY_*` environment values

## App and Importing

- `APP`
- `--factory`
- `--app-dir`

## Socket Binding

- `--host`
- `--port`
- `--uds`
- `--fd`

## Development and Reload

- `--reload`
- `--reload-dir` (repeatable)
- `--reload-include` (repeatable)
- `--reload-exclude` (repeatable)
- `--reload-delay`

## Workers and Process Controls

- `--workers`
- `--timeout-worker-healthcheck`
- `--limit-max-requests`
- `--limit-max-requests-jitter`

## Protocol and Interface

- `--loop`
- `--http`
- `--ws`
- `--lifespan`
- `--interface`
- `--h11-max-incomplete-event-size`

## HTTP behavior and limits

- `--root-path`
- `--limit-concurrency`
- `--backlog`
- `--timeout-keep-alive`
- `--timeout-graceful-shutdown`

## Logging and headers

- `--log-config`
- `--log-level`
- `--access-log / --no-access-log`
- `--use-colors / --no-use-colors`
- `--header` (repeatable `name:value`)
- `--server-header / --no-server-header`
- `--date-header / --no-date-header`

## Proxy and TLS

- `--proxy-headers / --no-proxy-headers`
- `--forwarded-allow-ips`
- `--ssl-keyfile`
- `--ssl-certfile`
- `--ssl-keyfile-password`
- `--ssl-version`
- `--ssl-cert-reqs`
- `--ssl-ca-certs`
- `--ssl-ciphers`

## Environment and startup extras

- `--env-file`
- `--version`

## Practical Runbook Advice

- Keep startup commands in version control, not shell history.
- Avoid combining `--reload` and multi-worker behavior in operational runbooks.
- Keep proxy trust explicit in production environments.
