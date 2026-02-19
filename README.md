# Palfrey

<p align="center">
  <a href="https://palfrey.dymmond.com"><img src="https://res.cloudinary.com/dymmond/image/upload/v1771522360/Palfrey/Logo/logo_ocxyty.png" alt='Palfrey'></a>
</p>

<p align="center">
    <em>Palfrey is a clean-room, high-performance Python ASGI server with source-traceable parity mapping.</em>
</p>

<p align="center">
<a href="https://github.com/dymmond/palfrey/actions/workflows/ci.yml/badge.svg?event=push&branch=main" target="_blank">
    <img src="https://github.com/dymmond/palfrey/actions/workflows/ci.yml/badge.svg?event=push&branch=main" alt="Test Suite">
</a>

<a href="https://pypi.org/project/palfrey" target="_blank">
    <img src="https://img.shields.io/pypi/v/palfrey?color=%2334D058&label=pypi%20package" alt="Package version">
</a>

<a href="https://pypi.org/project/palfrey" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/palfrey.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

**Documentation**: [https://palfrey.dev](https://palfrey.dev) 📚

**Source Code**: [https://github.com/dymmond/palfrey](https://github.com/dymmond/palfrey)

**The official supported version is always the latest released**.

---

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
- [Benchmarks](docs/en/docs/operations/benchmarks.md)
- [Release Process](docs/en/docs/operations/release-process.md)
