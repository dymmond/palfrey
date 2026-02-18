from __future__ import annotations

from palfrey import run

run(
    "docs_src.reference.programmatic_run:app",
    host="0.0.0.0",
    port=8443,
    ssl_certfile="./cert.pem",
    ssl_keyfile="./key.pem",
)
