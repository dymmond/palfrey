from __future__ import annotations

import os

PREFILL = {
    "PALFREY_APP": "myservice.main:app",
    "PALFREY_HOST": "0.0.0.0",
    "PALFREY_PORT": "8000",
    "PALFREY_LOG_LEVEL": "info",
}

for key, value in PREFILL.items():
    os.environ.setdefault(key, value)

print("Configured environment variables:")
for key in sorted(PREFILL):
    print(f"{key}={os.environ[key]}")
