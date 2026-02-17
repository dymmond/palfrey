# Deployment

```python
{!> ../../../docs_src/deployment/example.py !}
```

## Process supervision

Palfrey can run directly with workers, or under external process managers (systemd, supervisord, Kubernetes).

## TLS and proxy setups

- Configure TLS in-process with `--ssl-*` options.
- For reverse proxies, enable `--proxy-headers` and scope trusted proxy hops with `--forwarded-allow-ips`.
