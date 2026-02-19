# Benchmarks

Benchmark numbers are useful only when they are reproducible and tied to a specific environment.

## Latest sample baseline (February 19, 2026)

Command:

```bash
hatch run python benchmarks/run.py --http-requests 5000
```

Sample output:

| Scenario | Server | Operations | Duration (s) | Ops/s |
| --- | --- | ---: | ---: | ---: |
| http | palfrey | 5000 | 0.1426 | 35063.12 |
| http | uvicorn | 5000 | 0.2721 | 18374.60 |
| websocket | palfrey | 1000 | 0.0306 | 32631.40 |
| websocket | uvicorn | 1000 | 0.0702 | 14235.33 |

Relative throughput in this run:

- http: `1.908x` (Palfrey / Uvicorn)
- websocket: `2.292x` (Palfrey / Uvicorn)

Important:
These numbers are environment-specific and not universal guarantees.

## Benchmark principles

- compare equivalent runtime modes
- keep commands and environment details explicit
- run multiple samples and inspect variance
- include failure/error counts, not only throughput

## Suggested scenario matrix

1. small JSON API, high concurrency
2. mixed payload sizes and keep-alive reuse
3. websocket message throughput
4. reverse-proxy deployment path

## Reporting template

For each scenario, record:

- command line
- hardware and OS
- Python and dependency versions
- operations/sec
- p50/p95/p99 latency
- CPU and memory
- error count

## Communication rule

Never claim a performance improvement without the reproducible command, environment details, and raw results.
