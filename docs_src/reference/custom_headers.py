from __future__ import annotations

from palfrey.config import PalfreyConfig

config = PalfreyConfig(
    app="docs_src.reference.programmatic_run:app",
    headers=["x-service-name: billing-api", "x-environment: staging"],
    server_header=False,
)

print(config.normalized_headers)
