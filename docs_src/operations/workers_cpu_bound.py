from __future__ import annotations

from palfrey import run

if __name__ == "__main__":
    run(
        "docs_src.reference.programmatic_run:app",
        host="0.0.0.0",
        port=8000,
        workers=4,
        timeout_worker_healthcheck=10,
        backlog=2048,
    )
