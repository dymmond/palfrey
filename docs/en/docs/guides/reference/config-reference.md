# Config Reference

Palfrey exposes a typed `PalfreyConfig` model for programmatic startup.

```python
{!> ../../../docs_src/config/example.py !}
```

## Key fields

- `app`, `host`, `port`, `uds`, `fd`
- `reload*`, `workers`
- `loop`, `http`, `ws`, `lifespan`, `interface`
- `proxy_headers`, `forwarded_allow_ips`
- `limit_concurrency`, `limit_max_requests`, `timeout_keep_alive`
- `ssl_*`
- `headers`, `server_header`, `date_header`

## Notes

- `reload` and `workers > 1` are mutually exclusive.
- `reload`/`workers` require import-string app targets.
