# Benchmark Command Fix

**Date**: Wed Mar 11 2026
**Status**: ✅ RESOLVED

---

## Problem

The benchmark command `python -m benchmarks.run --http-requests 100000` was hanging indefinitely and timing out.

## Root Cause

The `.venv` environment was missing the **benchmark optional dependencies**, specifically:
- `uvicorn[standard]>=0.34.0` (required for performance comparison)
- `pytest-codspeed>=4.3.0` (required for codspeed integration)

The benchmark script spawns BOTH `palfrey` and `uvicorn` servers for head-to-head comparison:
- Palfrey server started successfully ✓
- Uvicorn server **failed to start** (module not found) ✗
- Script waited 20s for uvicorn port to become ready → timeout

## Solution

### Install Missing Dependencies

```bash
uv pip install -e ".[benchmark,standard]"
```

This installs:
- `uvicorn[standard]>=0.34.0` - Comparison ASGI server
- `pytest-codspeed>=4.3.0` - Performance tracking
- Plus all `standard` extras (httptools, uvloop, websockets, watchfiles)

### Verified Working Commands

**Option 1: Use installed script (RECOMMENDED)**
```bash
.venv/bin/palfrey-benchmark --http-requests 100000 --http-concurrency 20
```

**Option 2: Use module invocation**
```bash
.venv/bin/python -m benchmarks.run --http-requests 100000 --http-concurrency 20
```

**Option 3: Use wrapper script** (created for convenience)
```bash
./run-benchmark.sh --http-requests 100000 --http-concurrency 20
```

---

## Benchmark Results (Post-Fix)

### Full 100k HTTP Request Test

**Command**:
```bash
.venv/bin/palfrey-benchmark --http-requests 100000 --http-concurrency 20 --ws-clients 10 --ws-messages 1000
```

**Results**:

| Scenario | Server | Operations | Duration (s) | Ops/s |
| --- | --- | ---: | ---: | ---: |
| **HTTP** | palfrey | 100000 | 3.01 | **33,184** |
| **HTTP** | uvicorn | 100000 | 2.97 | **33,713** |
| **WebSocket** | palfrey | 10000 | 0.50 | **20,200** |
| **WebSocket** | uvicorn | 10000 | 0.51 | **19,771** |

**Relative Performance**:
- HTTP: **0.984x** (Palfrey / Uvicorn) → Palfrey slightly slower (~1.6% gap)
- WebSocket: **1.022x** (Palfrey / Uvicorn) → Palfrey faster (~2.2% faster)

**Note**: HTTP performance varies ±5% across runs due to system load, thermal throttling, and OS scheduler behavior. Multiple runs recommended for stable baseline.

---

## Environment Details

**System**:
- OS: macOS (Darwin Kernel Version 25.3.0, ARM64)
- CPU: Apple M4 Pro
- Python: 3.14.3

**Critical Dependencies**:
```
palfrey                         0.1.3       (local dev)
uvicorn                         0.41.0
httptools                       0.7.1
uvloop                          0.22.1
websockets                      16.0
pytest-codspeed                 4.3.0
```

---

## Files Modified

1. **Created**: `run-benchmark.sh` (wrapper script for convenience)
   - Ensures venv python is used
   - Passes all arguments through to `benchmarks.run`

2. **Updated**: `.venv/lib/python3.14/site-packages/` (installed 21 packages)

---

## Next Steps

### For Performance Testing

**Run full benchmark suite** (matches plan requirements):
```bash
./run-benchmark.sh --http-requests 100000 --http-concurrency 20 --ws-clients 10 --ws-messages 1000
```

**Run HTTP-only benchmark** (faster for HTTP-specific testing):
```bash
./run-benchmark.sh --http-requests 100000 --http-concurrency 20 --ws-clients 0 --ws-messages 0
```

**Run WebSocket-only benchmark**:
```bash
./run-benchmark.sh --http-requests 0 --http-concurrency 0 --ws-clients 20 --ws-messages 5000
```

**Export results as JSON** (for automated tracking):
```bash
./run-benchmark.sh --http-requests 100000 --json-output results.json
```

### For Wave 2 Performance Verification

After each committed optimization (Tasks 8, 11, 12), run:
```bash
./run-benchmark.sh --http-requests 100000 --http-concurrency 20 --ws-clients 0 --ws-messages 0
```

Compare against baseline:
- **Baseline HTTP**: ~33,000 ops/s (±5%)
- **Target**: 5-15% improvement after all Wave 2 optimizations

### For CI Integration

Add to GitHub Actions workflow:
```yaml
- name: Run benchmarks
  run: |
    uv pip install -e ".[benchmark,standard]"
    .venv/bin/palfrey-benchmark --http-requests 50000 --json-output benchmark-results.json
- name: Upload results to CodSpeed
  uses: CodSpeedHQ/action@v3
  with:
    token: ${{ secrets.CODSPEED_TOKEN }}
    run: pytest tests/ --codspeed
```

---

## Troubleshooting

### If benchmark still hangs

1. **Check venv activation**:
   ```bash
   which python  # Should show .venv/bin/python
   ```

2. **Verify uvicorn is installed**:
   ```bash
   .venv/bin/python -c "import uvicorn; print(uvicorn.__version__)"
   ```

3. **Test palfrey server manually**:
   ```bash
   .venv/bin/python -m palfrey benchmarks.apps:app --host 127.0.0.1 --port 8000
   curl http://127.0.0.1:8000/  # Should return "pong"
   ```

4. **Test uvicorn server manually**:
   ```bash
   .venv/bin/python -m uvicorn benchmarks.apps:app --host 127.0.0.1 --port 8001
   curl http://127.0.0.1:8001/  # Should return "pong"
   ```

### If results vary wildly (>10% difference across runs)

- Close background apps (browsers, IDEs, etc.)
- Disable Spotlight indexing temporarily
- Run multiple times and use median result
- Check CPU thermal throttling: `sudo powermetrics --samplers smc | grep -i "CPU die temperature"`

---

## Verification

✅ Benchmark command works
✅ Both palfrey AND uvicorn servers start successfully
✅ Results complete in reasonable time (<5s for 100k requests)
✅ Comparison metrics available (Palfrey / Uvicorn ratio)
✅ Wrapper script created for convenience

**Status**: READY FOR PERFORMANCE VERIFICATION
