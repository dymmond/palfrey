# Task 14 — Scenario 3: Rust vs Python fallback benchmark

Date: 2026-03-11

## Method

- Ran microbenchmarks in-process with warmup loops and `time.perf_counter()`.
- Measured four acceleration functions in two modes:
  - Rust enabled (default import path)
  - Python fallback forced (`PALFREY_NO_RUST=1`)

## Results (large representative inputs)

Ops/s values:

| Function | Rust enabled | Python fallback | Speedup (Rust/Python) |
| --- | ---: | ---: | ---: |
| `parse_header_items` | 59,431.19 | 63,597.36 | 0.93x |
| `split_csv_values` | 137,500.41 | 96,792.36 | 1.42x |
| `parse_request_head` | 88,301.72 | 90,285.49 | 0.98x |
| `unmask_websocket_payload` | 37,777.79 | 380.70 | **99.23x** |

## Interpretation

- Major throughput gain is in WebSocket payload unmasking (hot XOR path), where Rust is ~99x faster.
- String-heavy parsing paths are near parity in this environment; one (`split_csv_values`) shows a clear Rust win.
- Overall acceleration objective is met with significant benefit on the critical binary payload path.
