# Benchmarks

## Harness

Run reproducible comparisons with:

```bash
python -m benchmarks.run --json-output benchmark-results.json
```

The harness benchmarks two scenarios against `benchmarks.apps:app`:

- HTTP request throughput
- WebSocket echo throughput

## Latest run

Local run executed on February 17, 2026:

- Command:
  `python3 -m benchmarks.run --http-requests 10 --http-concurrency 2 --ws-clients 2 --ws-messages 2`
- Result:
  - `Benchmark for uvicorn failed: [Errno 1] Operation not permitted`
  - `Benchmark for palfrey failed: [Errno 1] Operation not permitted`
  - `http: n/a`
  - `websocket: n/a`

The current sandbox blocks local socket benchmarking (`Operation not permitted`), so throughput measurements are not
available from this run.

## Performance target

Target: 25-50% faster than Uvicorn in at least two realistic scenarios.

Current status: **not yet proven in this workspace run**. Palfrey includes benchmark tooling and Rust acceleration,
but no performance claim is made without measured output.

## Bottlenecks and next steps

- HTTP and WebSocket parsing are still predominantly Python-level hot paths.
- Reload/worker coordination currently prioritizes parity over throughput.
- Future work:
  1. Move request parsing and frame decode paths deeper into Rust.
  2. Add repeated-run statistics with confidence intervals.
  3. Profile end-to-end latency under mixed HTTP/WS load.
