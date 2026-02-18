# Guide: HTTPS / TLS

You can terminate TLS at a reverse proxy or directly in Palfrey.

## Recommended default

Terminate TLS at the edge proxy/load balancer when possible.
This centralizes certificate handling and reduces per-service TLS complexity.

## Direct TLS in Palfrey

```python
{!> ../../../docs_src/guides/https_run.py !}
```

CLI equivalent:

```bash
palfrey myapp.main:app \
  --ssl-certfile ./cert.pem \
  --ssl-keyfile ./key.pem \
  --host 0.0.0.0 --port 8443
```

## Optional client certificate settings

- `--ssl-cert-reqs`
- `--ssl-ca-certs`

## Operator reminders

- Rotate certificates before expiration.
- Validate cipher/protocol policy with your security team.
- Keep key material out of source control.
