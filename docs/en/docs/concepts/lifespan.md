# Lifespan

The ASGI lifespan protocol handles application startup and shutdown routines.

## Why use lifespan

Use it for resources that should exist for the process lifetime:

- database pools
- cache clients
- telemetry exporters
- warmup data

Example:

```python
{!> ../../../docs_src/concepts/lifespan_state.py !}
```

## Modes

- `--lifespan auto`: run when app supports it.
- `--lifespan on`: require lifespan handling.
- `--lifespan off`: skip lifespan protocol.

## Worker model note

Each worker process runs its own lifespan cycle.
If you run 4 workers, startup hooks run 4 times (once per worker).

## Shutdown expectations

On shutdown, Palfrey stops accepting new work, waits for in-flight tasks within configured limits, and then triggers lifespan shutdown.

## Non-Technical explanation

Lifespan is your open/close checklist:

- open the shop (startup)
- serve customers
- close cleanly (shutdown)
