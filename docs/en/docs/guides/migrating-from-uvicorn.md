# Guide: Migrating from Uvicorn

Palfrey was built with deep respect for Uvicorn and the ASGI ecosystem it helped mature. This is not a "winner vs loser" comparison. Uvicorn is an excellent, battle-tested server, and Palfrey intentionally keeps a compatible API/CLI experience so teams coming from Uvicorn feel at home. Our goal is to offer another strong option when teams want different internal architecture and extended runtime capabilities.

This guide helps you transition your existing Uvicorn-based deployments to Palfrey with minimal friction.

## 5-Step Migration Process

1.  **Audit current configuration**: Identify all Uvicorn CLI flags and environment variables currently in use.
2.  **Map to Palfrey equivalents**: Use the mapping tables below to find the corresponding Palfrey options.
3.  **Update deployment scripts**: Replace `uvicorn` commands with `palfrey` and update any `UVICORN_*` environment variables (though Palfrey mirrors these for backward compatibility).
4.  **Test locally**: Run your application with Palfrey in a development or staging environment with a traffic profile identical to your production load.
5.  **Gradual rollout**: Deploy Palfrey to a subset of your production nodes and monitor performance and stability before completing the rollout.

## CLI Flag Mapping

Palfrey maintains high parity with Uvicorn's CLI. Most flags work exactly as they do in Uvicorn.

| Uvicorn Flag | Palfrey Equivalent | Notes |
| --- | --- | --- |
| `APP` | `APP` | Import string (e.g., `main:app`). |
| `--host` | `--host` | Identical. |
| `--port` | `--port` | Identical. |
| `--uds` | `--uds` | Identical. |
| `--fd` | `--fd` | Identical. |
| `--workers` | `--workers` | Identical. |
| `--reload` | `--reload` | Identical. |
| `--reload-dir` | `--reload-dir` | Identical. |
| `--reload-delay` | `--reload-delay` | Identical. |
| `--reload-include` | `--reload-include` | Identical. |
| `--reload-exclude` | `--reload-exclude` | Identical. |
| `--log-level` | `--log-level` | Identical. |
| `--log-config` | `--log-config` | Identical. |
| `--access-log / --no-access-log` | `--access-log / --no-access-log` | Identical. |
| `--use-colors / --no-use-colors` | `--use-colors / --no-use-colors` | Identical. |
| `--loop` | `--loop` | Identical (`auto`, `asyncio`, `uvloop`). |
| `--http` | `--http` | Identical (`auto`, `h11`, `httptools`). Palfrey also adds `h2`, `h3`. |
| `--ws` | `--ws` | Identical (`auto`, `none`, `websockets`, `wsproto`). |
| `--lifespan` | `--lifespan` | Identical (`auto`, `on`, `off`). |
| `--interface` | `--interface` | Identical (`auto`, `asgi3`, `asgi2`, `wsgi`). |
| `--proxy-headers` | `--proxy-headers` | Identical. |
| `--forwarded-allow-ips` | `--forwarded-allow-ips` | Identical. |
| `--limit-concurrency` | `--limit-concurrency` | Identical. |
| `--limit-max-requests` | `--limit-max-requests` | Identical. |
| `--limit-max-requests-jitter` | `--limit-max-requests-jitter` | Identical. |
| `--timeout-keep-alive` | `--timeout-keep-alive` | Identical. |
| `--timeout-graceful-shutdown` | `--timeout-graceful-shutdown` | Identical. |

## Configuration Mapping

### Environment Variables

Palfrey uses the prefix `PALFREY_` for its environment variables. However, to make migration seamless, **Palfrey automatically mirrors `UVICORN_*` environment variables** to their `PALFREY_*` equivalents if no Palfrey-specific variable is defined.

| Uvicorn Env Var | Palfrey Env Var | Notes |
| --- | --- | --- |
| `UVICORN_HOST` | `PALFREY_HOST` | Automatically mirrored. |
| `UVICORN_PORT` | `PALFREY_PORT` | Automatically mirrored. |
| `UVICORN_WORKERS` | `PALFREY_WORKERS` | Automatically mirrored. |

### Configuration Files

Palfrey supports `.ini`, `.json`, and `.yaml` for logging configuration via `--log-config`, matching Uvicorn's support.

## Gunicorn Worker Migration

If you are running Uvicorn behind Gunicorn, you should update your worker class.

**Before (Uvicorn):**

```bash
gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
```

**After (Palfrey):**

```bash
gunicorn main:app -k palfrey.workers.PalfreyWorker -w 4 -b 0.0.0.0:8000
```

## Behavioral Differences

While Palfrey strives for parity, there are internal architectural differences that may result in subtly different behaviors:

*   **WebSocket Performance**: Palfrey often achieves significantly higher WebSocket throughput (up to 2.5x in benchmarks) due to its internal message orchestration layer.
*   **HTTP/2 and HTTP/3**: Palfrey includes native support for HTTP/2 and HTTP/3 which can be enabled via `--http h2` or `--http h3`.
*   **Strictness**: As a "clean-room" implementation, Palfrey might be stricter about certain ASGI spec edge cases that Uvicorn handles loosely.

## Common Gotchas

*   **Custom Worker Subclasses**: If you have custom subclasses of `uvicorn.workers.UvicornWorker`, you will need to port them to inherit from `palfrey.workers.PalfreyWorker`.
*   **Internal Uvicorn Imports**: If your application code imports from `uvicorn.*` internals, these will need to be updated to `palfrey.*` equivalents or refactored to use public ASGI interfaces.

## Example Comparison

### Uvicorn Deployment

```bash
{!> ../../../docs_src/migration/uvicorn_before.sh !}
```

### Palfrey Deployment

```bash
{!> ../../../docs_src/migration/palfrey_after.sh !}
```

## Verification Checklist

Use this checklist to ensure your migration is successful:

- [ ] **HTTP Connectivity**: Verify that standard GET/POST/etc. requests return the same status codes and payloads.
- [ ] **WebSocket Stability**: Confirm that WebSocket handshakes succeed and connections remain stable under load.
- [ ] **Lifespan Events**: Ensure that `startup` and `shutdown` events in your ASGI app are firing correctly.
- [ ] **Log Format**: Verify that logs are being captured correctly by your log management system.
- [ ] **Resource Usage**: Monitor CPU and Memory usage to ensure it meets your baseline expectations.
- [ ] **Performance**: Run benchmarks to confirm that throughput and latency are within acceptable ranges (refer to [Benchmarks](../operations/benchmarks.md)).

## Plain-Language Summary

Migrating from Uvicorn to Palfrey is designed to be a "drop-in" experience. Most CLI flags and environment variables are identical. The main change is replacing the command name and updating Gunicorn worker classes if used. Palfrey even respects your existing `UVICORN_` environment variables to make the transition as smooth as possible.
