# Benchmark Playbook

This playbook provides a step-by-step guide to reproducing Palfrey's performance benchmarks. We prioritize statistical validity and environment isolation to ensure results are meaningful and repeatable.

## Prerequisites

Before running benchmarks, ensure your environment meets these requirements:

- **Python**: 3.10 or newer (3.12+ recommended for best `uvloop` performance).
- **OS**: Linux (recommended for production-like network stack) or macOS.
- **Dependencies**: Install Palfrey with optional performance dependencies:
  ```bash
  pip install palfrey[httptools,uvloop,websockets] uvicorn
  ```

## Environment Setup

Performance numbers are highly sensitive to background noise. Follow these steps to isolate your benchmark run:

1. **Disable Turbo Boost**: If possible, disable CPU frequency scaling (Turbo Boost) to prevent thermal throttling from skewing results.
2. **Close Background Apps**: Ensure no heavy processes (browsers, IDEs, Docker containers) are running.
3. **CPU Pinning**: On Linux, consider using `taskset` to pin the benchmark process to specific cores.
4. **Network**: Use the loopback interface (`127.0.0.1`) to minimize network latency jitter, or a dedicated 10GbE+ link for remote testing.

## 3-Phase Methodology

Palfrey uses a 3-phase execution model to account for JIT warming and connection overhead:

1.  **Primer**: A small burst (10% of total load) to establish initial connections and trigger lazy imports.
2.  **Warmup**: A medium load (50% of total load) to allow the Python interpreter and event loop to optimize hot paths.
3.  **Measure**: The actual recorded run (100% of requested load).

## Running the Benchmark

The built-in benchmark harness compares Palfrey against Uvicorn using identical configurations (`httptools` parser and `uvloop` event loop).

### Standard HTTP Benchmark

To run a baseline HTTP test with 100,000 requests:

```bash
python -m benchmarks.run --http-requests 100000 --enable-phases
```

### Standard WebSocket Benchmark

To run a WebSocket echo test with 10 clients and 5,000 messages each:

```bash
python -m benchmarks.run --ws-clients 10 --ws-messages 5000 --enable-phases
```

### Combined Run with JSON Output

To run both and save results for machine analysis:

```bash
python -m benchmarks.run \
  --http-requests 50000 \
  --ws-clients 5 \
  --ws-messages 2000 \
  --enable-phases \
  --output results.json
```

## Interpreting Results

The harness provides several key metrics:

- **Ops/s (Throughput)**: The primary measure of how many operations the server handled per second.
- **Relative Speed**: Calculated as `Palfrey Ops/s / Uvicorn Ops/s`. A value > 1.0 means Palfrey is faster.
- **Statistical Summary**: When `--enable-phases` is used, the tool reports the standard deviation. A high standard deviation (relative to the mean) suggests a noisy environment.

## Benchmark Variations

You can vary the load profile using the following flags:

- `--http-concurrency`: Number of concurrent HTTP workers (default: 20).
- `--ws-clients`: Number of concurrent WebSocket connections.
- `--ws-messages`: Total messages per WebSocket client.

To test different ASGI applications, modify `benchmarks/apps.py`.

## Statistical Validity

Single runs are rarely enough for scientific comparison. We recommend:

1.  **Run multiple times**: Execute the playbook 3-5 times.
2.  **Check Variance**: If the standard deviation is more than 5% of the mean, identify and remove background interference.
3.  **Look at Medians**: Throughput peaks can be misleading; the median (reported in JSON output) is often more representative.

## Common Pitfalls

- **Docker Overhead**: Running benchmarks inside Docker on macOS/Windows introduces significant virtualization overhead. Always run natively for baseline numbers.
- **Thermal Throttling**: Laptops often slow down after 30-60 seconds of high CPU usage. Keep runs short or use active cooling.
- **Socket Exhaustion**: If you see `OSError: [Errno 49] Can't assign requested address`, you are exhausting ephemeral ports. Increase your OS limits or reduce concurrency.
- **Noisy Neighbors**: Other processes sharing the L3 cache or memory bandwidth can cause "stuttering" in results.

## Reporting Template

When reporting benchmark results, please include:

```markdown
### Environment
- **Hardware**: [e.g., M2 Pro, 16GB RAM]
- **OS**: [e.g., Ubuntu 22.04, macOS 14.2]
- **Python**: [e.g., 3.12.1]
- **Command**: `python -m benchmarks.run ...`

### Results
- **HTTP Ops/s**: Palfrey: X, Uvicorn: Y (Ratio: Zx)
- **WebSocket Ops/s**: Palfrey: A, Uvicorn: B (Ratio: Cx)
- **StdDev**: [Value from Statistical Summary]
```
