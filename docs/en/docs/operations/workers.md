# Workers

Workers run multiple server processes for parallelism and isolation.

## Why workers matter

- use multiple CPU cores
- isolate crashes to one process
- support rolling process replacement patterns

Reference app:

```python
{!> ../../../docs_src/operations/workers_cpu_bound.py !}
```

CLI example:

```bash
palfrey main:app --workers 4 --host 0.0.0.0 --port 8000
```

## Worker health and recycle controls

- `--timeout-worker-healthcheck`
- `--limit-max-requests`
- `--limit-max-requests-jitter`

## Sizing guidance

1. start near core count
2. benchmark realistic workload
3. observe CPU, memory, tail latency
4. adjust incrementally

## Important behavior notes

- each worker has independent memory/process state
- each worker runs its own lifespan startup/shutdown
- worker count can affect external dependency load (DB pool pressure)

## Non-technical summary

Workers are additional runtime lanes.
More lanes can increase throughput, but each lane consumes resources.
