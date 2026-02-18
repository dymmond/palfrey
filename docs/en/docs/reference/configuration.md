# Configuration Reference

This page documents `PalfreyConfig` fields and how they interact.

Programmatic example:

```python
{!> ../../../docs_src/reference/programmatic_config.py !}
```

## App Resolution

- `app`: callable or import string
- `factory`: treat import target as factory
- `app_dir`: additional import search directory
- `interface`: `auto|asgi3|asgi2|wsgi`

## Network Binding

- `host`, `port`
- `uds` (unix socket)
- `fd` (existing file descriptor)
- `backlog`

## Protocol Controls

- `loop`: `none|auto|asyncio|uvloop`
- `http`: `auto|h11|httptools`
- `ws`: `auto|none|websockets|websockets-sansio|wsproto`
- `lifespan`: `auto|on|off`
- `root_path`
- `h11_max_incomplete_event_size`

## WebSocket Controls

- `ws_max_size`
- `ws_max_queue`
- `ws_ping_interval`
- `ws_ping_timeout`
- `ws_per_message_deflate`

## Reload and Worker Controls

- `reload`
- `reload_dirs`
- `reload_includes`
- `reload_excludes`
- `reload_delay`
- `workers`
- `timeout_worker_healthcheck`

## Request limits and shutdown

- `limit_concurrency`
- `limit_max_requests`
- `limit_max_requests_jitter`
- `timeout_keep_alive`
- `timeout_graceful_shutdown`

## Logging and headers

- `log_config`
- `log_level`
- `access_log`
- `use_colors`
- `server_header`
- `date_header`
- `headers`

Header example:

```python
{!> ../../../docs_src/reference/custom_headers.py !}
```

## Proxy and TLS

- `proxy_headers`
- `forwarded_allow_ips`
- `ssl_keyfile`
- `ssl_certfile`
- `ssl_keyfile_password`
- `ssl_version`
- `ssl_cert_reqs`
- `ssl_ca_certs`
- `ssl_ciphers`

## Environment-derived defaults

- `workers` can default from `WEB_CONCURRENCY`.
- `forwarded_allow_ips` can default from `FORWARDED_ALLOW_IPS`.
- `reload_dirs` defaults to current directory when reload is enabled and no directory is specified.

## Important interactions

- Reload mode requires import-string app target.
- Worker mode requires import-string app target.
- `reload` and worker scale-out are operationally distinct modes.
