# Benchmarks

## Run commands

```python
{!> ../../../docs_src//benchmarks/run_benchmarks.py !}
```

## Current status

- Target: 25-50% faster than Uvicorn in at least two realistic scenarios.
- Current project status: benchmark harness exists; verifiable numbers depend on environment allowing socket benchmarks.

## Last local sandbox run (February 17, 2026)

- Command: `python3 -m benchmarks.run --http-requests 20 --http-concurrency 2 --ws-clients 2 --ws-messages 2`
- `Benchmark for uvicorn failed: [Errno 1] Operation not permitted`
- `Benchmark for palfrey failed: [Errno 1] Operation not permitted`

No performance claim is made without measured successful benchmark output.
