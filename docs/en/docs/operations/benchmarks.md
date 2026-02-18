# Benchmarks

Benchmarks are useful only when they are reproducible and representative.

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
