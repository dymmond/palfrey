# Palfrey Documentation

Palfrey is an ASGI server for Python applications.
This documentation is intentionally written for two audiences:

- Platform and product teams who need plain-language operational guidance.
- Backend engineers who need protocol-level detail and reproducible behavior.

## What Palfrey Is

Palfrey is the runtime process that sits between the network and your ASGI app.
It accepts connections, parses requests, runs your app callable, and writes responses back to clients.

In short:

- Your app decides business behavior.
- Palfrey decides network/process behavior.

## Who Should Read What

If you are new to ASGI:

1. [Installation](getting-started/installation.md)
2. [Quickstart](getting-started/quickstart.md)
3. [Terms and Mental Models](concepts/terms-and-mental-models.md)
4. [Deployment](operations/deployment.md)

If you run Uvicorn today and want to move safely:

1. [CLI Reference](reference/cli.md)
2. [Configuration Reference](reference/configuration.md)
3. [Server Behavior](concepts/server-behavior.md)

If your priority is reliability/performance:

1. [Event Loop](concepts/event-loop.md)
2. [Protocols](reference/protocols.md)
3. [Workers](operations/workers.md)
4. [Benchmarks](operations/benchmarks.md)

## First 60 Seconds

Create `main.py`:

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Start Palfrey:

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000
```

## Documentation Map

## Getting Started

- Install dependencies and optional extras.
- Run first HTTP app.
- Migrate baseline Uvicorn commands.

## Concepts

- ASGI callable and message model.
- Event loop selection.
- HTTP/WebSocket/lifespan lifecycle.
- Middleware and trust boundaries.
- Server behavior under load, errors, and shutdown.

## Reference

- Full CLI behavior and precedence.
- Configuration fields, defaults, interactions.
- Protocol surface and limits.
- Logging setup and structured config.

## Guides

- End-to-end production rollout.
- Reverse proxy integration.
- TLS setup.
- Troubleshooting cookbook.

## Operations

- Process model decisions.
- Reload and worker supervision.
- Docker pattern.
- Benchmark method and interpretation.
- Release process.

## Design Notes For Non-Technical Stakeholders

When someone asks, "what does this server buy us?", the answer is:

- Predictable startup and shutdown behavior.
- Clear process controls (single process, reload, workers).
- Explicit runtime configuration for repeatable deploys.
- Standard ASGI compatibility with modern Python frameworks.
