# Palfrey

Palfrey is a clean-room ASGI server implementation focused on high concurrency, predictable operations, and
source-traceable parity with Uvicorn behavior.

## Goals

- Uvicorn-compatible CLI flags where confirmed by Uvicorn docs/source.
- Original runtime implementation (no Uvicorn runtime dependency).
- Built-in reload and worker supervision.
- HTTP, WebSocket, and lifespan support.
- Optional Rust acceleration helpers with Python fallback.

## Documentation map

- Usage: install, quickstart, deployment, reload, workers.
- Reference: CLI and config behavior, protocols, logging.
- Validation: parity matrix and benchmark methodology.
- Release: OSS release process and CI gates.
