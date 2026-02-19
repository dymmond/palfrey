# Guide: From Zero to Production

This guide is an end-to-end path from local app to production operation.

## Stage 1: Local correctness

Goals:

- app starts reliably
- health endpoint returns expected status
- basic error paths are understood

Health-check starter app:

```python
{!> ../../../docs_src/guides/troubleshooting_healthcheck.py !}
```

Run locally:

```bash
palfrey main:app --host 127.0.0.1 --port 8000 --log-level debug
```

## Stage 2: Developer workflow

Use reload mode for rapid iteration:

```bash
palfrey main:app --reload --reload-dir src --reload-include '*.py'
```

Guardrails:

- do not use reload mode in production
- keep include/exclude patterns explicit

## Stage 3: Staging hardening

Checklist:

- run behind reverse proxy
- configure trusted forwarded IPs
- set explicit log level and access log behavior
- verify graceful shutdown behavior

## Stage 4: Production process model

Single process:

```bash
palfrey main:app --host 0.0.0.0 --port 8000
```

Multi-worker example:

```bash
palfrey main:app --host 0.0.0.0 --port 8000 --workers 4 --limit-max-requests 20000 --limit-max-requests-jitter 2000
```

Gunicorn + PalfreyWorker alternative:

```bash
gunicorn main:app -k palfrey.workers.PalfreyWorker -w 4 -b 0.0.0.0:8000
```

## Stage 5: Operational readiness

Minimum runbook should include:

- startup command
- rollback command
- health endpoints
- top 5 alerts
- owner on-call rotation

## Stage 6: Release and post-release checks

- run smoke tests immediately after deploy
- verify logs and metrics ingestion
- confirm expected error rate and latency window

## Non-technical rollout checklist

Before deploy:

- owner and rollback approver assigned
- success criteria documented
- abort criteria documented

After deploy:

- success criteria evaluated
- incident note recorded if deviations occurred
