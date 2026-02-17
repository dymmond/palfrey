# Migration From Uvicorn

Palfrey keeps the same major CLI option surface for confirmed Uvicorn features.

## Migration checklist

1. Replace `uvicorn` command with `palfrey`.
2. Keep existing options (`--host`, `--port`, `--reload`, `--workers`, `--proxy-headers`, `--ssl-*`, etc.).
3. Validate behavior against the [Parity Matrix](../parity-matrix.md).
4. Re-run your workload benchmarks in your environment.

## Clean-room note

Palfrey does not import or depend on Uvicorn at runtime.
