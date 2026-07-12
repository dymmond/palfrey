# Benchmarks

Benchmark numbers are useful only when they are reproducible and tied to a specific environment.

## Latest sample baseline (February 19, 2026)

Command:

```bash
hatch run python benchmarks/run.py --http-requests 100000 --http-concurrency 20 --ws-clients 0 --ws-messages 0 --samples 3 --output benchmarks/results/http-latest.json
```

Runtime modes are explicit: Palfrey runs with its default `--http auto` path, while the
comparison server runs with `--http httptools`; both use `uvloop`, disabled access logs,
and disabled proxy-header parsing.

Output shape:

| Scenario | Server | Operations | Failures | Duration (s) | Ops/s | p50 ms | p95 ms | p99 ms | Max ms | CPU s | Max RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| http | palfrey | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| http | uvicorn | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| websocket | palfrey | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| websocket | uvicorn | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Relative throughput in this run:

- http: `...x` (Palfrey / Uvicorn)
- websocket: `...x` (Palfrey / Uvicorn)

Important:
These numbers are environment-specific and not universal guarantees.

## Benchmark principles

- compare equivalent runtime modes
- keep commands and environment details explicit
- run multiple samples and inspect variance
- include failure/error counts, not only throughput
- retain raw JSON output when making performance claims

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
- maximum latency
- CPU and memory
- error count
- raw JSON output path

## Communication rule

Never claim a performance improvement without the reproducible command, environment details, and raw results.
