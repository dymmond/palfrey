# Palfrey

[![CI](https://github.com/dymmond/palfrey/actions/workflows/ci.yml/badge.svg)](https://github.com/dymmond/palfrey/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-blue)](https://github.com/dymmond/palfrey/actions/workflows/ci.yml)
[![Docs](https://github.com/dymmond/palfrey/actions/workflows/docs.yml/badge.svg)](https://github.com/dymmond/palfrey/actions/workflows/docs.yml)
[![Benchmarks](https://img.shields.io/badge/benchmarks-documented-success)](https://github.com/dymmond/palfrey/blob/main/docs/en/docs/operations/benchmarks.md)

Palfrey is a clean-room, high-performance Python ASGI server with source-traceable parity mapping to confirmed
Uvicorn behavior.

## Key points

- No runtime dependency on Uvicorn.
- Click-based CLI with Uvicorn-compatible option surface.
- HTTP, WebSocket, and lifespan protocol support.
- Loop setup modes and middleware stack (proxy headers, ASGI message logging).
- Reload and worker process supervision.
- Optional Rust acceleration helpers.

## Quick start

```bash
palfrey myapp.main:app --host 127.0.0.1 --port 8000
```

Programmatic startup:

```python
from palfrey import run

async def app(scope, receive, send):
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"hello"})

run(app)
```

## Quality gates

```bash
hatch run lint
hatch run check-types
hatch run test-cov
hatch run docs-build
```

## Docs

- [Overview](docs/en/docs/index.md)
- [Parity Matrix](docs/en/docs/parity-matrix.md)
- [Benchmarks](docs/en/docs/operations/benchmarks.md)
- [Testing Strategy](docs/en/docs/testing/testing-strategy.md)
- [Release Process](docs/en/docs/operations/release-process.md)
