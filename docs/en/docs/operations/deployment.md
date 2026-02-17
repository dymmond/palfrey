# Deployment

## Worker process mode

```python
{!> ../../../docs_src//workers/workers_cli.py !}
```

## TLS

```python
{!> ../../../docs_src//ssl/ssl_cli.py !}
```

## Process manager guidance

For production, run Palfrey under an external supervisor (systemd, Kubernetes, etc.) and configure graceful shutdown
policies to align with worker lifecycle settings.
