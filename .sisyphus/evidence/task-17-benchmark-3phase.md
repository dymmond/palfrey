
=== 3-Phase Benchmark Mode ===
Python: 3.14.3
OS: Darwin
CPU: arm
Loop: asyncio


--- UVICORN ---
Phase: PRIMER (HTTP 1000 requests)
Phase: WARMUP (HTTP 5000 requests)
Phase: MEASURE (HTTP 10000 requests)

--- PALFREY ---
Phase: PRIMER (HTTP 1000 requests)
Phase: WARMUP (HTTP 5000 requests)
Phase: MEASURE (HTTP 10000 requests)

| Scenario | Server | Operations | Duration (s) | Ops/s |
| --- | --- | ---: | ---: | ---: |
| http | palfrey | 10000 | 0.2921 | 34231.90 |
| http | uvicorn | 10000 | 0.2973 | 33632.87 |
- http: 1.018x (Palfrey / Uvicorn)
- websocket: n/a

=== Statistical Summary ===

UVICORN:
  http:
    ops/s: 33632.87
    stddev: 0.00

PALFREY:
  http:
    ops/s: 34231.90
    stddev: 0.00
