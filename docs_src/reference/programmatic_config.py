from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.runtime import run

config = PalfreyConfig(
    app="docs_src.reference.programmatic_run:app",
    host="0.0.0.0",
    port=9000,
    workers=1,
    proxy_headers=True,
    limit_concurrency=100,
    timeout_keep_alive=10,
)

run(config)
