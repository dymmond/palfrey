# Server Behavior

This page describes runtime behavior that matters during incidents and scale events.

## Connection lifecycle

1. accept connection
2. parse request(s)
3. execute ASGI app
4. write response
5. keep alive or close

For WebSocket upgrades, flow switches from HTTP request lifecycle to websocket event lifecycle.

## Limits and overload behavior

- `--limit-concurrency` caps in-flight work
- excess load receives `503 Service Unavailable`
- request/response parser limits protect memory and CPU

## Header behavior

- optional default `server` and `date` headers
- connection handling based on protocol/headers
- response content length/chunking normalized on write

## Graceful shutdown model

On shutdown signal, Palfrey:

1. stops accepting new connections
2. waits for active tasks/connections to drain
3. enforces `--timeout-graceful-shutdown` when set
4. runs lifespan shutdown when enabled

Graceful handling example:

```python
{!> ../../../docs_src/operations/graceful_shutdown.py !}
```

## Worker recycle behavior

`--limit-max-requests` and jitter can be used to rotate workers over time and avoid synchronized restarts.

## Plain-language explanation

Server behavior defines what happens when things are busy or broken.
The goal is controlled degradation, not sudden failure.
