# Quickstart

This quickstart moves from easy to advanced in one page.

## Stage 1: Hello World (Easy)

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Run:

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

Check:

```bash
curl http://127.0.0.1:8000
```

## Stage 2: JSON Response (Easy)

```python
{!> ../../../docs_src/getting_started/json_api.py !}
```

Start with reload in development:

```bash
palfrey main:app --reload --reload-dir .
```

## Stage 3: Read Request Body (Intermediate)

```python
{!> ../../../docs_src/concepts/http_read_body.py !}
```

This pattern is useful for webhooks and JSON APIs that process request payloads.

## Stage 4: WebSocket Echo (Intermediate)

```python
{!> ../../../docs_src/concepts/websocket_echo.py !}
```

Run with explicit websocket mode:

```bash
palfrey main:app --ws websockets
```

## Stage 5: App Factory (Intermediate)

```python
{!> ../../../docs_src/getting_started/factory_app.py !}
```

Run with `--factory`:

```bash
palfrey --factory main:create_app
```

## Stage 6: Programmatic Startup (Advanced)

```python
{!> ../../../docs_src/reference/programmatic_run.py !}
```

Use this when Palfrey startup is coordinated by another Python process.

## Stage 7: Environment-Driven Configuration (Advanced)

```python
{!> ../../../docs_src/reference/env_runtime.py !}
```

Typical shell usage:

```bash
export PALFREY_HOST=0.0.0.0
export PALFREY_PORT=9000
palfrey main:app
```

## Stage 8: Pick a Production Direction

- reverse proxy setup: [Reverse Proxy (Nginx)](../guides/reverse-proxy-nginx.md)
- TLS strategy: [HTTPS and TLS](../guides/https-tls.md)
- process model: [Workers](../operations/workers.md)
- reliability behavior: [Server Behavior](../concepts/server-behavior.md)

## Stage 9: Gunicorn + PalfreyWorker (Advanced)

Use this when you want Gunicorn process supervision with Palfrey protocol/runtime handling.

```bash
gunicorn main:app -k palfrey.workers.PalfreyWorker -w 4 -b 0.0.0.0:8000
```

Alternate worker class (h11-specific):

```bash
gunicorn main:app -k palfrey.workers.PalfreyH11Worker -w 4 -b 0.0.0.0:8000
```

Example Gunicorn config file:

```python
{!> ../../../docs_src/operations/gunicorn_conf.py !}
```

## Non-Technical Summary

You just learned three maturity levels:

- basic app startup
- practical development workflow
- production-oriented runtime control
