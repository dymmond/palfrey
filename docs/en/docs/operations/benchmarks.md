# Benchmarks

Benchmarks are useful only when they are reproducible and representative.

## Latest baseline (February 19, 2026)

Command:

```bash
hatch run python benchmarks/run.py --json-output benchmarks/results/latest.json
```

Results:

| Scenario | Server | Operations | Duration (s) | Ops/s |
| --- | --- | ---: | ---: | ---: |
| http | palfrey | 2000 | 0.1537 | 13011.70 |
| http | uvicorn | 2000 | 0.1538 | 13000.42 |
| websocket | palfrey | 1000 | 0.0587 | 17021.65 |
| websocket | uvicorn | 1000 | 0.0491 | 20382.30 |

Relative throughput:

- http: `1.001x` (Palfrey / Uvicorn)
- websocket: `0.835x` (Palfrey / Uvicorn)

Artifacts:

- JSON output: `benchmarks/results/latest.json`

## Benchmark principles

- compare equivalent startup modes and protocol settings
- include warmup and steady-state windows
- measure latency distribution, not only average throughput
- keep hardware/software environment documented

## Example command builder

```python
{!> ../../../docs_src/operations/benchmark_plan.py !}
```

## Suggested scenario matrix

1. JSON API, small payload, high concurrency
2. mixed read/write payloads with keep-alive traffic
3. WebSocket echo throughput and frame-size distribution
4. proxy-terminated deployment shape

## Reporting template

For each scenario capture:

- requests/sec or messages/sec
- p50/p95/p99 latency
- CPU and memory
- error rate/timeouts
- exact runtime command lines

## Communication guidance

Do not claim performance gains without published reproducible measurements and environment details.

## Current bottlenecks and next work

- WebSocket throughput is currently below Uvicorn in this benchmark shape.
- Known hotspot areas: frame read/write loop overhead, masking/unmasking path, and backend dispatch path costs.
- Planned next work:
  - deeper Rust acceleration for frame parse/encode fast paths
  - reduced Python object churn in websocket send/receive loops
  - scenario-specific tuning and regression benchmarks in CI
