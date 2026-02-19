# Lifespan

Lifespan is the ASGI startup/shutdown channel.

## Why lifespan exists

Use it for process-wide resources:

- database pools
- cache clients
- outbound HTTP clients
- telemetry exporters

Example app:

```python
{!> ../../../docs_src/concepts/lifespan_state.py !}
```

## Lifespan modes

- `--lifespan auto`: run when app supports lifespan
- `--lifespan on`: require lifespan behavior
- `--lifespan off`: disable lifespan channel

## Worker model impact

Each worker process runs its own lifespan cycle.
If you run 4 workers, startup/shutdown hooks run 4 times.

## Startup/shutdown expectations

Startup:

1. Palfrey sends startup event
2. app initializes resources
3. app confirms startup complete

Shutdown:

1. Palfrey stops accepting new work
2. drains in-flight work within limits
3. sends shutdown event
4. app releases resources

## Plain-language explanation

Lifespan is the opening and closing checklist for the app process.
When done correctly, deploys and restarts become predictable.
