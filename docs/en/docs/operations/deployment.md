# Deployment

This page describes deployment models from simple to production-grade.

## Model 1: Single process

```bash
palfrey main:app --host 0.0.0.0 --port 8000
```

Best for:

- internal tools
- low-traffic services
- early-stage prototypes

## Model 2: Multi-worker process

```bash
palfrey main:app --host 0.0.0.0 --port 8000 --workers 4
```

Best for:

- CPU scaling across cores
- process isolation for resilience

## Model 3: Reverse proxy + Palfrey

- edge proxy handles ingress policy and TLS
- Palfrey handles ASGI runtime and protocol behavior
- trusted proxy boundaries configured explicitly

## Model 4: Service manager supervised

Use `systemd` (or equivalent) for:

- restart policy
- startup ordering
- log routing
- boot integration

Reference app:

```python
{!> ../../../docs_src/operations/systemd_app.py !}
```

## Model 5: Gunicorn supervisor with Palfrey workers

Use Gunicorn when your platform standardizes around Gunicorn process supervision.

Direct command:

```bash
gunicorn main:app -k palfrey.workers.PalfreyWorker -w 4 -b 0.0.0.0:8000
```

Config-driven startup:

```python
{!> ../../../docs_src/operations/gunicorn_conf.py !}
```

```bash
gunicorn main:app -c docs_src/operations/gunicorn_conf.py
```

## Model 6: HTTP/3 edge service (QUIC)

Use this when you need HTTP/3 transport explicitly.

```bash
palfrey main:app --http h3 --ws none --host 0.0.0.0 --port 8443 --ssl-certfile cert.pem --ssl-keyfile key.pem
```

Operational notes:

- traffic is UDP-based at the edge
- ensure security groups / firewall rules allow UDP on the selected port
- `--uds` and `--fd` startup modes are not used in HTTP/3 mode

## Production checklist

- startup command is explicit and versioned
- health checks (`/healthz`) are in place
- proxy trust config reviewed
- graceful shutdown tested
- rollback command documented

## Non-technical summary

Deployment maturity should match business risk.
As reliability requirements grow, move from simple process startup to managed process supervision and controlled ingress.
