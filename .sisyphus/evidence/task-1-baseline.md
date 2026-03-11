# Task 1: Performance Baseline - Palfrey vs Uvicorn

**Date**: Wed Mar 11 2026
**Baseline Captured**: ✓ YES (ready for optimization work)

---

## Environmental Metadata

### System
- **OS**: macOS (Darwin Kernel Version 25.3.0, ARM64)
- **CPU**: Apple M4 Pro
- **Python Version**: 3.14.3 (`/opt/homebrew/bin/python3`)

### Installed Packages (Critical for Reproducibility)
```
palfrey                         0.1.3       (local dev)
uvicorn                         0.41.0
httptools                       0.7.1
uvloop                          0.22.1
websockets                      16.0
```

---

## Benchmark Methodology Analysis

### Runner: `benchmarks/run.py`

**Phases Observed**: ✓ YES - 3-phase methodology confirmed
1. **Primer Phase**: `_wait_for_port(port, timeout=20.0)` - Server ready check (line 54-62)
2. **Warmup Phase**: IMPLICIT - None observed (benchmark runs immediately after server ready)
3. **Measure Phase**: Core testing with threading (lines 282-317 for HTTP, 404-435 for WebSocket)

**Thread Model**: Multi-threaded per-scenario
- HTTP: `requests // concurrency` split across threads (line 288)
- WebSocket: Single message sequence per thread (line 423)

**Connection Strategy**:
- HTTP: Keep-alive reuse with final connection close (line 169)
- WebSocket: Persistent single connection per thread with echo verify (line 397-399)

**Test Workload** (`benchmarks/apps.py`):
- HTTP: Simple echo responding with `b"pong"` + `content-type: text/plain` header
- WebSocket: Echo service validating payload match (line 37)

### Benchmark Configuration
```
Default (hatch run benchmark):
- HTTP requests:     2000
- HTTP concurrency:  20 (threads)
- WebSocket clients: 1
- WebSocket msgs:    1000 per client
```

---

## Baseline Results (Default Configuration)

### Run 1
```
| Scenario   | Server  | Operations | Duration (s) | Ops/s    |
|------------|---------|------------|--------------|----------|
| http       | palfrey | 2000       | 0.0598       | 33427.58 |
| http       | uvicorn | 2000       | 0.0594       | 33655.51 |
| websocket  | palfrey | 1000       | 0.0309       | 32348.24 |
| websocket  | uvicorn | 1000       | 0.0690       | 14499.56 |
```

**Relative Performance**:
- HTTP: Palfrey 0.993x Uvicorn (Palfrey SLIGHTLY SLOWER by 0.7%)
- WebSocket: Palfrey 2.231x Uvicorn (Palfrey SIGNIFICANTLY FASTER by 123%)

### Run 2 (Consistency Check)
```
| Scenario   | Server  | Operations | Duration (s) | Ops/s    |
|------------|---------|------------|--------------|----------|
| http       | palfrey | 2000       | 0.0605       | 33036.80 |
| http       | uvicorn | 2000       | 0.0587       | 34059.73 |
| websocket  | palfrey | 1000       | 0.0295       | 33952.06 |
| websocket  | uvicorn | 1000       | 0.0675       | 14824.88 |
```

**Relative Performance**:
- HTTP: Palfrey 0.970x Uvicorn (Palfrey SLIGHTLY SLOWER by 3.0%)
- WebSocket: Palfrey 2.290x Uvicorn (Palfrey SIGNIFICANTLY FASTER by 129%)

### Consistency Verification
| Metric | Run 1 | Run 2 | Variance | Status |
|--------|-------|-------|----------|--------|
| Palfrey HTTP | 33427.58 | 33036.80 | 1.18% | ✓ STABLE |
| Uvicorn HTTP | 33655.51 | 34059.73 | 1.20% | ✓ STABLE |
| Palfrey WebSocket | 32348.24 | 33952.06 | 4.97% | ✓ ACCEPTABLE |
| Uvicorn WebSocket | 14499.56 | 14824.88 | 2.24% | ✓ STABLE |

**Conclusion**: Variance < 5% within acceptable measurement noise. Results are reproducible.

---

## Socket Options Audit

### Current Configuration (`palfrey/config.py:618`)
```python
sock = socket.socket(family=family)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# ... bind socket ...
```

**Socket Options Currently Set**:
- ✓ `SO_REUSEADDR` = 1 (Allow quick rebind after restart)

**Socket Options NOT Currently Set**:
- ✗ `TCP_NODELAY` - Not found (NAGLE algorithm active - potential buffering latency)
- ✗ `SO_REUSEPORT` - Not found (Single process binding, no port sharing)
- ✗ Custom `backlog` - Uses default `2048` (`palfrey/config.py:314`)

**Analysis**:
- TCP_NODELAY would disable Nagle's algorithm, reducing latency on small packets
- SO_REUSEPORT would enable SO_REUSEPORT for load balancing (not applicable to single process)
- Backlog of 2048 is substantial; typical value is 128

**Opportunity**: TCP_NODELAY is a candidate for HTTP micro-optimization.

---

## Status Line Generation Audit

### Current Implementation (`palfrey/protocols/http.py:690-694`)
```python
try:
    reason = http.HTTPStatus(response.status).phrase
except ValueError:
    reason = ""

parts: list[bytes] = [f"HTTP/1.1 {response.status} {reason}\r\n".encode("ascii")]
```

**Status Line Encoding**:
- ✓ Dynamic reason phrase lookup via `http.HTTPStatus()`
- ✓ Fallback to empty reason for custom status codes
- ✗ No pre-computed cache for common status codes (200, 301, 404, 500)
- ✗ Status line built fresh per response via f-string and encode

**Analysis**:
- Common HTTP responses (200, 301, 404, 500) encode same status line every time
- Example: `HTTP/1.1 200 OK\r\n` is regenerated for every 200 response
- Pre-computing top 10-15 status codes would save:
  - 1x `http.HTTPStatus()` lookup (O(1) but non-zero)
  - 1x f-string format operation
  - 1x `.encode("ascii")` call

**Opportunity**: Status line caching for top-N most-common status codes.

### Current Common Status Codes in Test Workload
- `200 OK` - 100% of requests in benchmark (echo response)
- No 301, 404, 500 in baseline test (simple echo app)

**Pre-Compute Candidates**:
```
TOP CANDIDATES (by RFC 9110 + web analytics):
1. 200 OK
2. 301 Moved Permanently
3. 304 Not Modified
4. 400 Bad Request
5. 401 Unauthorized
6. 403 Forbidden
7. 404 Not Found
8. 500 Internal Server Error
9. 502 Bad Gateway
10. 503 Service Unavailable
```

---

## Variation Testing Plan (Deferred)

These variations MUST be tested after baseline is established:

### Variation A: Uvloop Only (no httptools)
```bash
hatch run python -m palfrey benchmarks.apps:app \
  --loop uvloop --http h1 --port {PORT}
```
**Expected Impact**: Likely slower HTTP (httptools is optimized parser)

### Variation B: Asyncio (no uvloop)
```bash
hatch run python -m palfrey benchmarks.apps:app \
  --loop asyncio --http httptools --port {PORT}
```
**Expected Impact**: Slower on both HTTP and WebSocket (asyncio is slower than uvloop)

### Variation C: No asyncio enhancement (pure stdlib)
```bash
hatch run python -m palfrey benchmarks.apps:app \
  --loop asyncio --http h1 --port {PORT}
```
**Expected Impact**: Slowest configuration

**Note**: These variations require custom benchmark harness (not standard `hatch run benchmark` CLI).

---

## Key Findings Summary

| Category | Finding | Status | Action |
|----------|---------|--------|--------|
| **Performance Parity** | HTTP ~0.98x Uvicorn, WebSocket ~2.26x | ✓ BASELINE | Document baseline |
| **Consistency** | < 5% run-to-run variance | ✓ VERIFIED | Proceed to optimization |
| **TCP_NODELAY** | NOT configured (Nagle active) | ⚠ OPPORTUNITY | Task 2+ (socket opts) |
| **Status Line Cache** | Dynamic generation every response | ⚠ OPPORTUNITY | Task 2+ (HTTP micro-opts) |
| **Backlog** | 2048 (adequate, no tuning needed yet) | ✓ ADEQUATE | Monitor in load test |
| **Multiplexing** | httptools + uvloop hardcoded | ⚠ LOCKED | Consider configurable backend |

---

## Next Steps

1. **Wave 1 Baseline Complete**: ✓ This document
2. **Wave 1 Tasks 2-7**: Apply micro-optimizations based on findings above
3. **Post-Wave 1**: Re-capture baseline with optimization applied
4. **Variations Testing**: Run variation scenarios after optimization plateau

---

## Reproducibility Command

To re-run this baseline:

```bash
cd /Users/tarsil/Projects/github/dymmond/palfrey
hatch run benchmark  # Run twice, record results
hatch run python3 -m pip list | grep -E "(palfrey|httptools|uvloop|uvicorn)"
python3 --version && uname -a
```

**Expected Result**: Within 5% of values shown in "Baseline Results" section.
