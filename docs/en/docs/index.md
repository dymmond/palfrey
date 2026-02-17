# Palfrey

Palfrey is a clean-room ASGI server implementation focused on production runtime behavior parity with Uvicorn while
remaining fully independent at runtime.

## What Palfrey provides

- Click CLI with Uvicorn-compatible option names (where confirmed by source docs/code).
- HTTP/1.1 request handling and response lifecycle.
- WebSocket handshake and frame handling.
- Lifespan startup/shutdown flow.
- Process supervision for reload mode and worker mode.
- Proxy-header and message-logger middleware support.
- Optional Rust acceleration for parser hot paths.

## Documentation structure

- **Getting Started**: installation, quickstart, migration.
- **Concepts**: event loop, HTTP, WebSockets, lifespan, middleware.
- **Reference**: CLI, config, protocols, logging.
- **Operations**: deploy, reload, workers, benchmarks, release process.
- **Validation**: parity matrix and testing strategy.

## Source-backed parity policy

Palfrey only claims parity for behavior grounded in:

- Uvicorn docs at [uvicorn.dev](https://uvicorn.dev/)
- Uvicorn source files under [`uvicorn/`](https://github.com/Kludex/uvicorn/tree/main/uvicorn)
- Click docs/source for command parsing semantics

See [Parity Matrix](parity-matrix.md) for detailed mapping.
