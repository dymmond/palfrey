from __future__ import annotations

COMMANDS = [
    "palfrey myapp.main:app",
    "palfrey myapp.main:app --reload --reload-dir src",
    "palfrey myapp.main:app --workers 4 --host 0.0.0.0 --port 8000",
    "palfrey myapp.main:app --proxy-headers --forwarded-allow-ips 10.0.0.0/8,127.0.0.1",
]

for command in COMMANDS:
    print(command)
