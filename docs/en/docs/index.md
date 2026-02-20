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

**Documentation**: [https://palfrey.dymmond.com](https://palfrey.dymmond.com) 📚

**Source Code**: [https://github.com/dymmond/palfrey](https://github.com/dymmond/palfrey)

**The official supported version is always the latest released**.

---

Palfrey is a clean-room ASGI server focused on three things:

- behavior you can reason about
- deployment controls you can operate safely
- performance you can reproduce and verify

Protocol runtime modes include HTTP/1.1 backends plus opt-in HTTP/2 (`--http h2`) and HTTP/3 (`--http h3`) paths.

## Palfrey vs Uvicorn

Palfrey was built with deep respect for Uvicorn and the ASGI ecosystem it helped mature.
This is not a "winner vs loser" comparison. Uvicorn is an excellent, battle-tested server, and Palfrey intentionally keeps a compatible API/CLI experience so teams coming from Uvicorn feel at home.
Our goal is to offer another strong option when teams want different internal architecture and extended runtime capabilities.

Benchmark snapshot (your run):

- Command: `python -m benchmarks.run --http-requests 100000`

| Scenario | Palfrey Ops/s | Uvicorn Ops/s | Relative Speed |
| --- | ---: | ---: | ---: |
| HTTP | 36859.67 | 36357.47 | `1.014x` |
| WebSocket | 38884.53 | 15317.18 | `2.539x` |

These numbers are environment-dependent. Always benchmark with your own app, traffic profile, and infrastructure before making production decisions.

This documentation is written for both technical and non-technical readers.

- Engineers can use the protocol details, option tables, and runbooks.
- Product, support, and operations teams can use the plain-language summaries and checklists.

## What Palfrey Does

At runtime, Palfrey sits between clients and your ASGI application.

1. accepts TCP or UNIX socket connections
2. parses protocol bytes into ASGI events
3. calls your app with `scope`, `receive`, `send`
4. writes responses back to clients
5. manages process behavior (reload, workers, graceful shutdown)

## Who Should Start Where

## If you are new to ASGI

1. [Installation](getting-started/installation.md)
2. [Quickstart](getting-started/quickstart.md)
3. [Terms and Mental Models](concepts/terms-and-mental-models.md)
4. [Server Behavior](concepts/server-behavior.md)

## If you operate production services

1. [Deployment](operations/deployment.md)
2. [Workers](operations/workers.md)
3. [Observability](operations/observability.md)
4. [Troubleshooting](guides/troubleshooting.md)
5. [Release Process](operations/release-process.md)

## First 60 Seconds

Create `main.py`:

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Run Palfrey:

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

Check it:

```bash
curl http://127.0.0.1:8000
```

Gunicorn + Palfrey worker:

```bash
gunicorn main:app -k palfrey.workers.PalfreyWorker -w 4 -b 0.0.0.0:8000
```

## Documentation Structure

## Getting Started

- install, verify, and run your first app
- move from a minimal app to real startup patterns

## Concepts

- what ASGI is, and how Palfrey applies it
- how HTTP, WebSocket, and lifespan flows behave
- how server internals affect user-visible outcomes

## Reference

- full CLI and config surface
- protocol and logging behavior
- env var model and common errors

## Guides

- migration, security hardening, production rollout
- practical troubleshooting and FAQ

## Operations

- deployment shapes, workers, reload model
- capacity planning, observability, benchmark method
- platform-specific notes and release process

## Plain-Language Summary

If your application is the business logic, Palfrey is the runtime control layer around it.
A good runtime control layer gives teams:

- predictable startup and shutdown
- fewer surprises under traffic spikes
- clearer incident response paths
- safer, repeatable deployments
