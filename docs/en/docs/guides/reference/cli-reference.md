# CLI Reference

Palfrey CLI is implemented with Click and tracks confirmed Uvicorn option names and argument semantics.

## Usage

```bash
palfrey [OPTIONS] APP
```

## Confirmed option groups

- Socket binding: `--host`, `--port`, `--uds`, `--fd`
- Development/reload: `--reload`, `--reload-dir`, `--reload-include`, `--reload-exclude`, `--reload-delay`
- Workers/process: `--workers`, `--timeout-worker-healthcheck`
- Protocol selection: `--loop`, `--http`, `--ws`, `--lifespan`, `--interface`
- WebSocket controls: `--ws-max-size`, `--ws-max-queue`, `--ws-ping-interval`, `--ws-ping-timeout`
- Logging: `--log-config`, `--log-level`, `--access-log`, `--use-colors`
- Proxy headers: `--proxy-headers`, `--forwarded-allow-ips`
- TLS: `--ssl-keyfile`, `--ssl-certfile`, `--ssl-keyfile-password`, `--ssl-version`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers`
- Response defaults: `--header`, `--server-header`, `--date-header`
- App import controls: `--app-dir`, `--factory`

See [Parity Matrix](../../parity-matrix.md) for exact source mapping.
