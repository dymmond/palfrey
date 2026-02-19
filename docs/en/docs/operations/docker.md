# Docker

This page covers practical container deployment patterns.

## Probe-ready app example

```python
{!> ../../../docs_src/operations/docker_healthcheck.py !}
```

## Minimal Dockerfile

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir palfrey

EXPOSE 8000
CMD ["palfrey", "docs_src.operations.docker_healthcheck:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Recommended multi-stage pattern

Use multi-stage builds when compiling optional components or installing build-only dependencies.

## Runtime flags often used in containers

- `--host 0.0.0.0`
- `--port 8000`
- `--workers N` (when resource limits justify)
- proxy flags when behind ingress

## Container health checks

Configure orchestrator probes for:

- liveness
- readiness

Example endpoint choices:

- `/healthz`
- `/readyz`

## Operational recommendations

- keep base images pinned
- keep images minimal
- avoid embedding secrets in image layers
- keep startup command explicit and reviewed

## Non-technical summary

Containers package runtime behavior into repeatable units.
Repeatability is what makes staging and production comparable.
