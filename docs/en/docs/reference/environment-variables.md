# Environment Variables

Palfrey CLI uses `PALFREY_` environment variable prefix.

## Core behavior

- Click maps CLI options to `PALFREY_*` env vars.
- CLI flags override env vars.
- Palfrey mirrors `UVICORN_*` vars to `PALFREY_*` when no Palfrey-specific value is set.

Example runtime setup:

```python
{!> ../../../docs_src/reference/env_runtime.py !}
```

## Common examples

```bash
export PALFREY_APP=main:app
export PALFREY_HOST=0.0.0.0
export PALFREY_PORT=8000
export PALFREY_LOG_LEVEL=info
palfrey
```

Uvicorn compatibility bridge example:

```bash
export UVICORN_HOST=0.0.0.0
export UVICORN_PORT=8000
palfrey main:app
```

## High-value variables to set explicitly

- `PALFREY_APP`
- `PALFREY_HOST`
- `PALFREY_PORT`
- `PALFREY_WORKERS`
- `PALFREY_LOG_LEVEL`
- `PALFREY_FORWARDED_ALLOW_IPS`

## Environment-specific recommendations

## Development

Use env vars for convenience, but keep final startup command visible in scripts.

## CI

Pin all runtime-critical values explicitly for reproducibility.

## Production

Keep secrets out of CLI arguments and logs.
Use secret stores or secure env injection.

## Plain-language summary

Environment variables are a convenient way to parameterize startup without editing code.
