# Task 7 — HTTP Hot Path Profiling Report

Date: 2026-03-11
Environment: macOS (darwin), Hatch env Python 3.13.12, HTTP benchmark app (`benchmarks.apps:app`)

## Profiling Commands Executed

1. Installed profiler in project env:

```bash
hatch run python -m pip install py-spy
```

2. Server-side cProfile under realistic HTTP load (50k requests, benchmark-style threaded keep-alive clients):

```bash
hatch run python -m cProfile -o .sisyphus/evidence/task-7-cprofile.prof -m palfrey benchmarks.apps:app --host 127.0.0.1 --port 8765 --no-access-log --http httptools --loop uvloop --ws websockets --limit-max-requests 50000
```

3. py-spy attempt (blocked by OS permissions):

```bash
hatch run py-spy record -o .sisyphus/evidence/task-7-flamegraph.svg --pid <PID> --duration 30
```

Observed error on macOS:

```text
This program requires root on OSX.
Try running again with elevated permissions by going 'sudo !!'
```

## Top 10 Functions by Cumulative Time (HTTP Hot Path)

Source: `.sisyphus/evidence/task-7-cprofile.prof`, filtered to Palfrey HTTP request/response pipeline symbols.

| Rank | Function | Cum Time (s) | Own Time (s) | Calls |
|---:|---|---:|---:|---:|
| 1 | `palfrey.server:run` | 3.507258 | 0.000002 | 1 |
| 2 | `palfrey.server:_handle_connection` | 2.025784 | 0.130740 | 50063 |
| 3 | `palfrey.server:_handle_http_request` | 1.116395 | 0.073969 | 50000 |
| 4 | `palfrey.server:_queue_connection_requests` | 0.970744 | 0.052202 | 50023 |
| 5 | `palfrey.protocols.http:run_http_asgi` | 0.726835 | 0.072313 | 50000 |
| 6 | `palfrey.middleware.proxy_headers:__call__` | 0.626983 | 0.063436 | 50002 |
| 7 | `palfrey.protocols.http:read_http_request` | 0.558832 | 0.091084 | 100023 |
| 8 | `palfrey.server:_write_response` | 0.423174 | 0.033940 | 50000 |
| 9 | `palfrey.protocols.http:encode_http_response` | 0.342373 | 0.194237 | 50000 |
| 10 | `palfrey.middleware.proxy_headers:__contains__` | 0.321615 | 0.030285 | 50000 |

## Top 10 Functions by Own Time (Excluding Callees)

| Rank | Function | Own Time (s) | Cum Time (s) | Calls |
|---:|---|---:|---:|---:|
| 1 | `palfrey.protocols.http:encode_http_response` | 0.194237 | 0.342373 | 50000 |
| 2 | `palfrey.server:_handle_connection` | 0.130740 | 2.025784 | 50063 |
| 3 | `palfrey.protocols.http:send` | 0.117066 | 0.186701 | 100000 |
| 4 | `palfrey.protocols.http:build_http_scope` | 0.100904 | 0.180495 | 50000 |
| 5 | `palfrey.protocols.http:_header_lookup` | 0.099288 | 0.163876 | 200000 |
| 6 | `palfrey.protocols.http:read_http_request` | 0.091084 | 0.558832 | 100023 |
| 7 | `palfrey.protocols.http:_parse_request_head_httptools` | 0.086954 | 0.204643 | 50000 |
| 8 | `palfrey.server:_handle_http_request` | 0.073969 | 1.116395 | 50000 |
| 9 | `palfrey.protocols.http:run_http_asgi` | 0.072313 | 0.726835 | 50000 |
| 10 | `palfrey.middleware.proxy_headers:__call__` | 0.063436 | 0.626983 | 50002 |

## Flame Graph Observations

- `py-spy` installation succeeded, but flame graph capture was blocked by macOS privilege requirements (`root` needed to sample target process).
- Result: **no `.sisyphus/evidence/task-7-flamegraph.svg` produced in this non-root session**.
- Workaround to complete this evidence item in CI or local privileged shell:

```bash
sudo $(hatch run which py-spy) record -o .sisyphus/evidence/task-7-flamegraph.svg --pid <PID> --duration 30
```

or launch under py-spy with equivalent elevated permissions.

## Optimization Opportunities Mapped to Tasks 8–14

### Task 8 — Streaming HTTP response writer
- Evidence: `encode_http_response` is #1 by own time (0.194s); `_write_response` is also top-10 cumulative.
- Opportunity: stop full-response aggregation/copying and stream status line + headers + body chunks directly.

### Task 9 — Zero-copy header handling
- Evidence: `build_http_scope` + `_header_lookup` + `_parse_request_head_httptools` are all top own-time functions.
- Opportunity: keep headers as bytes through parser/scope path; reduce normalize/lookup overhead.

### Task 10 — Remove unconditional body joins in request read path
- Evidence: `read_http_request` is top-10 in both cumulative and own time.
- Opportunity: avoid unconditional concatenation for single-chunk/common cases; streamline chunk handling.

### Task 11 — Socket tuning
- Evidence (global benchmark profile): socket `recv/sendall` dominate total runtime in client/server interaction loops.
- Opportunity: validate transport/socket options (e.g., `TCP_NODELAY`, backlog, reuse flags) and tune for lower I/O overhead under concurrency.

### Task 12 — Precomputed status lines + cached header fragments
- Evidence: serialization path cost concentrated in `encode_http_response`.
- Opportunity: cache byte status lines and frequently emitted header bytes to reduce per-request formatting costs.

### Task 13 — HTTP write backpressure
- Evidence: `_write_response` remains materially hot and participates in high cumulative server time.
- Opportunity: improve write/drain strategy to avoid burst write penalties and flatten tail latency under load.

### Task 14 — Rust extension optimization
- Evidence: hottest pure-Python work includes request parsing/scope/header operations.
- Opportunity: selectively accelerate parser/scope/header primitives where Python overhead remains significant.

## Summary

Profiling confirms the suspected hotspots are real: `encode_http_response`, `build_http_scope`, `read_http_request`, and `_write_response` are all significant in the HTTP hot path. Wave 2 tasks should prioritize Tasks **8, 9, 10, and 12** first (highest direct CPU leverage), then **13/11**, with **14** focused on proven remaining Python-heavy primitives.
