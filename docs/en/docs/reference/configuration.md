# Configuration Reference

`PalfreyConfig` is the typed runtime configuration model.

```python
{!> ../../../docs_src//config/example.py !}
```

## Key behavior

- `workers`: defaults from `$WEB_CONCURRENCY`, fallback `1`.
- `forwarded_allow_ips`: defaults from `$FORWARDED_ALLOW_IPS`, fallback `127.0.0.1`.
- `reload`: when enabled and `reload_dirs` is empty, defaults to current working directory.
- `headers`: accepts tuple pairs or `"name: value"` strings.

## Validation rules

- `workers >= 1`
- `reload` and `workers > 1` cannot be combined
- reload/worker modes require import-string app target
