# CLI Reference

Palfrey CLI uses Click with `auto_envvar_prefix=PALFREY`.

Command shape:

```bash
palfrey [OPTIONS] APP
```

- `APP` is usually `module:attribute`.
- use `--factory` when the target returns an ASGI app callable.

Example command set:

```python
{!> ../../../docs_src/cli/basic_commands.py !}
```

## Configuration precedence

Highest to lowest:

1. CLI options
2. `PALFREY_*` environment variables
3. config defaults

Note:
Palfrey also mirrors `UVICORN_*` env vars to `PALFREY_*` when no Palfrey-specific value is set.

## Option reference

## App loading

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `APP` | arg | required | import target such as `main:app` |
| `--factory` | flag | `false` | treat APP as factory callable |
| `--app-dir` | str | `""` | prepend path to import search |
| `--interface` | choice | `auto` | `auto`, `asgi3`, `asgi2`, `wsgi` |

## Bind and sockets

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--host` | str | `127.0.0.1` | bind host |
| `--port` | int | `8000` | bind port |
| `--uds` | str | `None` | unix domain socket path |
| `--fd` | int | `None` | inherited socket descriptor |
| `--backlog` | int | `2048` | listen queue size |

## Protocol runtime

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--loop` | str | `auto` | `none`, `auto`, `asyncio`, `uvloop` |
| `--http` | str | `auto` | `auto`, `h11`, `httptools` |
| `--ws` | str | `auto` | `auto`, `none`, `websockets`, `websockets-sansio`, `wsproto` |
| `--lifespan` | choice | `auto` | `auto`, `on`, `off` |
| `--h11-max-incomplete-event-size` | int | `None` | h11 buffer cap |

## WebSocket tuning

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--ws-max-size` | int | `16777216` | max websocket message bytes |
| `--ws-max-queue` | int | `32` | queue size for websocket backend |
| `--ws-ping-interval` | float | `20.0` | ping period seconds |
| `--ws-ping-timeout` | float | `20.0` | ping timeout seconds |
| `--ws-per-message-deflate` | bool | `true` | compression toggle |

## Reload and workers

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--reload` | flag | `false` | enable file-watch reload mode |
| `--reload-dir` | repeat str | `[]` | watch roots |
| `--reload-include` | repeat str | `[]` | include patterns |
| `--reload-exclude` | repeat str | `[]` | exclude patterns |
| `--reload-delay` | float | `0.25` | scan delay |
| `--workers` | int | `None` | worker process count |
| `--timeout-worker-healthcheck` | int | `5` | worker heartbeat timeout |
| `--limit-max-requests` | int | `None` | recycle worker after N requests |
| `--limit-max-requests-jitter` | int | `0` | additional randomized recycle offset |

## Request limits and shutdown

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--limit-concurrency` | int | `None` | max active tasks/connections |
| `--timeout-keep-alive` | int | `5` | idle keep-alive timeout |
| `--timeout-graceful-shutdown` | int | `None` | shutdown drain timeout |
| `--root-path` | str | `""` | ASGI root path override |

## Logging and headers

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--log-config` | path | `None` | `.ini`, `.json`, `.yaml` |
| `--log-level` | choice | `None` | `critical`, `error`, `warning`, `info`, `debug`, `trace` |
| `--access-log / --no-access-log` | flag | `true` | access log toggle |
| `--use-colors / --no-use-colors` | flag | `None` | terminal color control |
| `--header` | repeat str | `[]` | custom default response header |
| `--server-header / --no-server-header` | flag | `true` | default Server header |
| `--date-header / --no-date-header` | flag | `true` | default Date header |

## Proxy and TLS

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--proxy-headers / --no-proxy-headers` | flag | `true` | parse trusted forwarded headers |
| `--forwarded-allow-ips` | str | `None` | trusted proxy sources list |
| `--ssl-keyfile` | str | `None` | TLS private key |
| `--ssl-certfile` | str | `None` | TLS certificate |
| `--ssl-keyfile-password` | str | `None` | key password |
| `--ssl-version` | int | `ssl.PROTOCOL_TLS_SERVER` | TLS protocol selector |
| `--ssl-cert-reqs` | int | `ssl.CERT_NONE` | client cert requirement |
| `--ssl-ca-certs` | str | `None` | CA bundle path |
| `--ssl-ciphers` | str | `TLSv1` | cipher suite policy |

## Misc

| Option | Type | Default | Notes |
| --- | --- | --- | --- |
| `--env-file` | path | `None` | dotenv-style env file |
| `--version` | flag | n/a | print version and exit |

## Practical command recipes

## API server, simple

```bash
palfrey myapp.main:app --host 0.0.0.0 --port 8000
```

## Local development

```bash
palfrey myapp.main:app --reload --reload-dir src --log-level debug
```

## Multi-worker deployment

```bash
palfrey myapp.main:app --workers 4 --limit-max-requests 20000 --limit-max-requests-jitter 2000
```

## Behind reverse proxy

```bash
palfrey myapp.main:app --proxy-headers --forwarded-allow-ips 127.0.0.1
```

## Plain-language summary

The CLI is your runtime control panel.
If startup commands are explicit and versioned, operations become predictable.
