# Workers and Process Model

Workers increase parallelism by running multiple server processes.

## Why workers

- better CPU utilization for concurrent workloads
- isolation from single-process crashes
- rolling worker replacement strategies

## Starter example

```python
{!> ../../../docs_src/operations/workers_cpu_bound.py !}
```

CLI equivalent:

```bash
palfrey myapp.main:app --workers 4 --host 0.0.0.0 --port 8000
```

## Health and restart controls

- `--timeout-worker-healthcheck`
- `--limit-max-requests`
- `--limit-max-requests-jitter`

## Capacity planning guidance

- start with worker count near available CPU cores
- benchmark with realistic concurrency and payload patterns
- adjust for memory constraints and external dependency bottlenecks

## Non-Technical translation

More workers are like more checkout counters.
They increase throughput, but each counter consumes staff/resources.
