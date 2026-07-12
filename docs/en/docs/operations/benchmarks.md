# Benchmarks

Benchmark numbers are useful only when they are reproducible and tied to a specific environment.

## Latest HTTP sample baseline (July 12, 2026)

Command:

```bash
hatch run python benchmarks/run.py --http-requests 100000 --http-concurrency 50 --ws-clients 0 --ws-messages 0 --samples 5
```

Runtime modes are explicit: Palfrey runs with its default `--http auto` path, while the
comparison server runs with `--http httptools`; both use `uvloop`, disabled access logs,
and disabled proxy-header parsing.

Sample output:

| Scenario | Server | Operations | Failures | Duration (s) | Ops/s | p50 ms | p95 ms | p99 ms | Max ms | CPU s | Max RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| http | palfrey | 500000 | 0 | 14.2791 | 35016.18 | 1.238 | 3.131 | 4.335 | 21.330 | 11.515 | 35930112 |
| http | uvicorn | 500000 | 0 | 15.0808 | 33154.69 | 1.288 | 3.369 | 5.051 | 21.342 | 10.616 | 38469632 |

Relative throughput in this run:

- http: `1.056x` (Palfrey / Uvicorn)
- websocket: n/a for this HTTP-only run

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
