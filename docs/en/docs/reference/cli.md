# CLI Reference

Palfrey CLI is Click-based and tracks Uvicorn's option names where parity is confirmed.

## Usage

```bash
palfrey [OPTIONS] APP
```

## Option groups

- Socket: `--host`, `--port`, `--uds`, `--fd`
- Reload: `--reload`, `--reload-dir`, `--reload-include`, `--reload-exclude`, `--reload-delay`
- Workers: `--workers`, `--timeout-worker-healthcheck`
- Protocol: `--loop`, `--http`, `--ws`, `--lifespan`, `--interface`
- WebSocket: `--ws-max-size`, `--ws-max-queue`, `--ws-ping-interval`, `--ws-ping-timeout`, `--ws-per-message-deflate`
- Logging: `--log-config`, `--log-level`, `--access-log`, `--use-colors`
- Proxy: `--proxy-headers`, `--forwarded-allow-ips`
- TLS: `--ssl-keyfile`, `--ssl-certfile`, `--ssl-keyfile-password`, `--ssl-version`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers`
- App import: `--app-dir`, `--factory`
- Parser limit: `--h11-max-incomplete-event-size`

## Click references

- Click docs: [Options](https://click.palletsprojects.com/en/stable/options/)
- Click docs: [Commands and Groups](https://click.palletsprojects.com/en/stable/commands-and-groups/)
- Click source: `src/click/core.py`
