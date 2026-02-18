# Server Behavior

This page documents runtime behavior that matters for reliability and incident response.

## Connection lifecycle

- Palfrey accepts TCP/Unix socket connections.
- Reads one HTTP request at a time per connection.
- Optionally keeps connection alive for follow-up requests.
- Closes on timeout, protocol error, or explicit close behavior.

## Header behavior

- Optional default `server` and `date` headers are injected unless disabled.
- If `Content-Length` is missing, payload length is calculated before send.
- Connection header is managed based on keep-alive decisions.

## Request limits and protection

- `--limit-concurrency` caps active request handlers.
- Overflow requests receive `503 Service Unavailable`.
- Request head/body limits protect against oversized payload abuse.

## Graceful shutdown

- Signals trigger shutdown event.
- Server socket stops accepting new connections.
- In-flight work is allowed to finish within configured boundaries.
- Lifespan shutdown runs when enabled.

Graceful work example:

```python
{!> ../../../docs_src/operations/graceful_shutdown.py !}
```

## Worker restart behavior

With `--limit-max-requests`, each process can exit after N requests (plus optional jitter) so supervisors replace workers over time.

## Non-Technical explanation

Server behavior defines what happens in bad weather: high load, malformed traffic, deploy restarts, and partial failures.
Predictable behavior is what keeps outages smaller.
