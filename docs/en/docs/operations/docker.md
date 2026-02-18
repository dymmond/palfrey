# Docker Operations

This page covers practical container deployment with Palfrey.

## Example app for container probes

```python
{!> ../../../docs_src/operations/docker_healthcheck.py !}
```

## Minimal Dockerfile pattern

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir palfrey

EXPOSE 8000
CMD ["palfrey", "docs_src.operations.docker_healthcheck:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Container health checks

Add health probes in your orchestrator against `/healthz` and `/readyz`.

## Runtime flags commonly used in containers

- `--host 0.0.0.0`
- `--port <container-port>`
- `--workers <n>` when CPU resources justify it
- proxy settings when behind ingress/proxy

## Image and runtime recommendations

- Use pinned base image tags.
- Keep runtime images minimal; move build tooling to separate build stages.
- Avoid embedding secrets in images.
- Keep startup command explicit and versioned.

## Non-Technical explanation

Containerizing Palfrey packages runtime behavior into a repeatable unit,
so staging and production execute the same startup logic.
