"""Example Gunicorn config using Palfrey worker classes."""

from __future__ import annotations

bind = "0.0.0.0:8000"
workers = 4
worker_class = "palfrey.workers.PalfreyWorker"

# Optional Gunicorn settings that interact with Palfrey worker runtime.
keepalive = 5
timeout = 30
max_requests = 20000
max_requests_jitter = 2000

# Forwarded header trust can also be controlled in Gunicorn settings.
forwarded_allow_ips = "127.0.0.1"
