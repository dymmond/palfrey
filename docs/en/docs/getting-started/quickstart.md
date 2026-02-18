# Quickstart

This guide starts from minimal HTTP and progressively adds real-world patterns.

## Step 1: Minimal HTTP App

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Run:

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

## Step 2: JSON API Response

```python
{!> ../../../docs_src/getting_started/json_api.py !}
```

Run with live reload while developing:

```bash
palfrey main:app --reload --reload-dir .
```

## Step 3: Application Factory

Use a factory when object construction is non-trivial.

```python
{!> ../../../docs_src/getting_started/factory_app.py !}
```

Start with factory mode:

```bash
palfrey --factory main:create_app
```

## Step 4: Programmatic Startup

Use Python startup when embedding server launch in your own process flow.

```python
{!> ../../../docs_src/reference/programmatic_run.py !}
```

## Step 5: Environment-Driven Runtime

Palfrey CLI supports `PALFREY_*` env vars via Click `auto_envvar_prefix`.

```python
{!> ../../../docs_src/reference/env_runtime.py !}
```

## Step 6: Next Learning Path

- Request/response mechanics: [HTTP Concepts](../concepts/http.md)
- Real-time connections: [WebSockets](../concepts/websockets.md)
- Startup/shutdown orchestration: [Lifespan](../concepts/lifespan.md)
- Production planning: [Zero to Production](../guides/from-zero-to-production.md)

## Plain-Language Summary

At this point you have learned:

- How to start an app quickly.
- How to use auto-reload during development.
- How to move from toy examples to controlled startup patterns.
