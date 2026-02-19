# Guide: HTTPS and TLS

You can terminate TLS at the edge proxy or directly in Palfrey.

## Recommended default

For most production systems, terminate TLS at the edge (load balancer or reverse proxy).

Benefits:

- centralized certificate management
- consistent security policy across services
- simpler app runtime configuration

## Direct TLS in Palfrey

Programmatic example:

```python
{!> ../../../docs_src/guides/https_run.py !}
```

CLI example:

```bash
palfrey main:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-certfile ./cert.pem \
  --ssl-keyfile ./key.pem
```

## Optional client certificate controls

- `--ssl-cert-reqs`
- `--ssl-ca-certs`

## Hardening recommendations

- rotate certificates before expiry
- store keys securely (never in source control)
- keep cipher policy aligned with security requirements
- test renewal and restart procedure before production deadline

## Validation checklist

- handshake succeeds with expected certificate chain
- health endpoints accessible over HTTPS
- logs reflect secure scheme where expected

## Non-technical summary

TLS is the encrypted channel between clients and your service.
You can place encryption at the front door (proxy) or inside the app runtime.
