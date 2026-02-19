# Configuration

This page documents `PalfreyConfig` and key interactions.

Programmatic setup example:

```python
{!> ../../../docs_src/reference/programmatic_config.py !}
```

## Core fields

| Field | Default | Meaning |
| --- | --- | --- |
| `app` | required | ASGI app or import string |
| `factory` | `False` | treat app target as factory |
| `app_dir` | `cwd` | import search path |
| `interface` | `auto` | `auto`, `asgi3`, `asgi2`, `wsgi` |
| `lifespan` | `auto` | startup/shutdown protocol mode |

## Binding and sockets

| Field | Default | Meaning |
| --- | --- | --- |
| `host` | `127.0.0.1` | bind host |
| `port` | `8000` | bind port |
| `uds` | `None` | unix socket path |
| `fd` | `None` | inherited socket descriptor |
| `backlog` | `2048` | kernel listen queue |

## Protocol selection

| Field | Default | Meaning |
| --- | --- | --- |
| `loop` | `auto` | event loop policy |
| `http` | `auto` | HTTP implementation |
| `ws` | `auto` | websocket implementation |
| `h11_max_incomplete_event_size` | `None` | h11 incomplete event cap |

## WebSocket controls

| Field | Default | Meaning |
| --- | --- | --- |
| `ws_max_size` | `16777216` | max websocket payload |
| `ws_max_queue` | `32` | websocket queue cap |
| `ws_ping_interval` | `20.0` | ping interval seconds |
| `ws_ping_timeout` | `20.0` | ping timeout seconds |
| `ws_per_message_deflate` | `True` | compression behavior |

## Reload and workers

| Field | Default | Meaning |
| --- | --- | --- |
| `reload` | `False` | enable reload supervisor |
| `reload_dirs` | `[]` | explicit watch roots |
| `reload_includes` | `[]` | include patterns |
| `reload_excludes` | `[]` | exclude patterns |
| `reload_delay` | `0.25` | watch delay |
| `workers` | `None` | worker process count |
| `timeout_worker_healthcheck` | `5` | worker health timeout |

## Request and process limits

| Field | Default | Meaning |
| --- | --- | --- |
| `limit_concurrency` | `None` | active in-flight cap |
| `limit_max_requests` | `None` | worker recycle threshold |
| `limit_max_requests_jitter` | `0` | randomized recycle offset |
| `timeout_keep_alive` | `5` | keep-alive idle timeout |
| `timeout_graceful_shutdown` | `None` | graceful drain timeout |

## Logging and headers

| Field | Default | Meaning |
| --- | --- | --- |
| `log_config` | internal dict config | logging setup |
| `log_level` | `None` | logger level override |
| `access_log` | `True` | access log toggle |
| `use_colors` | `None` | colorized log output toggle |
| `server_header` | `True` | inject Server header |
| `date_header` | `True` | inject Date header |
| `headers` | `[]` | extra default headers |

Header example:

```python
{!> ../../../docs_src/reference/custom_headers.py !}
```

## Proxy and TLS

| Field | Default | Meaning |
| --- | --- | --- |
| `proxy_headers` | `True` | parse forwarded headers |
| `forwarded_allow_ips` | env/default | trusted proxy sources |
| `ssl_keyfile` | `None` | TLS key |
| `ssl_certfile` | `None` | TLS cert |
| `ssl_keyfile_password` | `None` | key passphrase |
| `ssl_version` | `ssl.PROTOCOL_TLS_SERVER` | TLS protocol selection |
| `ssl_cert_reqs` | `ssl.CERT_NONE` | client cert requirement |
| `ssl_ca_certs` | `None` | CA path |
| `ssl_ciphers` | `TLSv1` | cipher policy |

## Important interactions

- `reload=True` requires app import string target.
- `workers>1` requires app import string target.
- `wsgi` interface disables websocket support (`effective_ws = none`).
- explicit backend selection requires corresponding dependency installed.

## Environment defaults

- `workers` may default from `WEB_CONCURRENCY`
- `forwarded_allow_ips` may default from `FORWARDED_ALLOW_IPS`
- reload dirs default to current working directory when reload is enabled and none supplied

## Plain-language summary

Configuration is a contract for how your service should behave in every environment.
Keep it explicit and versioned.
