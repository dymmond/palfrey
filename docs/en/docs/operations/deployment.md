# Deployment

This page describes deployment patterns from simple to production-grade.

## Level 1: Single process

```bash
palfrey myapp.main:app --host 0.0.0.0 --port 8000
```

Use for prototypes, internal tools, and low-concurrency services.

## Level 2: Multi-worker process model

```bash
palfrey myapp.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Use when one process cannot safely saturate available CPU.

## Level 3: Reverse proxy in front

- Edge proxy handles ingress policy and TLS.
- Palfrey handles app runtime and protocol behavior.
- Trust forwarded headers only from explicit proxy IP ranges.

Example app used for proxy diagnostics:

```python
{!> ../../../docs_src/guides/nginx_reverse_proxy_app.py !}
```

## Level 4: Service manager supervision

Use `systemd`/equivalent for restart policy, log routing, and boot ordering.

Service app reference:

```python
{!> ../../../docs_src/operations/systemd_app.py !}
```

## Level 5: Controlled restarts under load

Consider:

- `--limit-max-requests`
- `--limit-max-requests-jitter`
- `--timeout-graceful-shutdown`

These settings help long-running services avoid synchronized worker churn.

## Production readiness checklist

- health endpoints and alarms configured
- proxy trust boundaries explicit
- graceful shutdown tested with in-flight requests
- rollback command documented
- capacity test results captured

## Non-Technical decision aid

Scale deployment maturity when one of these becomes true:

- response latency degrades at peak load
- uptime requirements increase
- compliance/security requires stricter ingress controls
- incident handling needs deterministic restart behavior
