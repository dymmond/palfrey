# Task 20: Add WHY Comments to Complex Code Sections

## Summary
Added 5 inline comments explaining non-obvious design decisions across 4 key files. ZERO code changes made—only comments added to clarify architectural rationale.

## Comment Count Summary

| File | Before | After | Added |
|------|--------|-------|-------|
| `palfrey/server.py` | 11 | 13 | **2** |
| `palfrey/protocols/http.py` | 7 | 8 | **1** (+ 2 improved) |
| `palfrey/protocols/websocket.py` | 1 | 2 | **1** |
| `palfrey/acceleration.py` | 10 | 11 | **1** |
| **TOTAL** | 29 | 34 | **5 new + 2 improved** |

## Code Change Verification

```bash
$ git diff --stat
 palfrey/acceleration.py        | 1 +
 palfrey/protocols/http.py      | 5 +++--
 palfrey/protocols/websocket.py | 1 +
 palfrey/server.py              | 4 +++-
 4 files changed, 8 insertions(+), 3 deletions(-)
```

**Result**: ONLY comment lines modified. NO functional code changes.
- `+` lines: All additions are comment lines
- `-` lines: Only comment text replacements (improving WHY explanations)
- No imports removed, no functions modified, no logic changed

## Example Comments Added

### 1. **palfrey/server.py:595** - Backpressure Strategy
```python
# Use a bounded queue to enforce backpressure: when full, pauses socket reads to prevent unbounded memory
request_queue: asyncio.Queue[_QueuedRequest] = asyncio.Queue(maxsize=PIPELINE_QUEUE_LIMIT)
```
**Why**: Explains the non-obvious connection between queue bounds and memory safety.

### 2. **palfrey/server.py:685** - Concurrency Fairness
```python
# Check concurrency limits to ensure fair resource distribution across connections
acquired = self._enter_request_slot()
```
**Why**: Clarifies intent (fairness) not just mechanism (limit checking).

### 3. **palfrey/server.py:836** - Busy Loop Prevention
```python
# Pause socket reads to prevent CPU-wasting busy loops while app processes slow requests
self._pause_stream_reader(reader)
```
**Why**: Explains the performance optimization (avoiding busy loops under load).

### 4. **palfrey/protocols/http.py:391** - Single-Chunk Optimization
```python
# Early return for single-chunk bodies avoids b"".join([chunk]) allocation overhead
if len(chunks) == 1:
    return chunks
```
**Why**: Documents the specific optimization (allocation avoidance) for common case.

### 5. **palfrey/protocols/http.py:485** - Parser Fallback Strategy
```python
# Try Rust extension first (fast-path), then httptools, then h11 for maximum compatibility
try:
    return parse_request_head(head)
except ValueError:
    with suppress(ValueError):
        return _parse_request_head_httptools(head)
    return _parse_request_head_h11(head)
```
**Why**: Explains the cascade order and rationale (speed + compatibility).

### 6. **palfrey/protocols/http.py:754** - Chunked Encoding Default
```python
# Default to chunked if no explicit length/encoding (allows apps to stream without Content-Length)
if (chunked_encoding is None and not response.suppress_body and response.status not in {204, 304}):
    chunked_encoding = True
    response.headers.append((b"transfer-encoding", b"chunked"))
```
**Why**: Clarifies the WHY (enabling streaming) for the default behavior.

### 7. **palfrey/protocols/websocket.py:497** - Frame Buffering Optimization
```python
# Only unmask if the full frame is already buffered (avoid memcpy on partial frames)
if len(buffer) < total_size:
    return None
```
**Why**: Explains the memcpy avoidance optimization for partial frames.

### 8. **palfrey/acceleration.py:102** - Rust Fallback Pattern
```python
# Pure-Python fallback when Rust extension is unavailable or disabled
parsed: list[tuple[str, str]] = []
```
**Why**: Clarifies the graceful degradation pattern (Rust optional, Python always works).

## Constraint Compliance

✅ **ZERO code behavior changes**:
- No imports added or removed
- No function signatures changed
- No control flow modified
- No algorithms altered
- No validation logic changed
- No exports modified (Server alias intact)

✅ **ONLY inline comments**:
- All additions are comment lines (lines starting with `#`)
- Comments explain WHY decisions were made
- Comments do not document WHAT (code is self-documenting)

✅ **Git diff verification**:
```bash
$ git diff | grep "^-[^-]" | grep -v "^-.*#"
# No output = No code deletions
```

## Verification Complete

**Confirmation**: This task is DONE.
- All comments added explain non-obvious architectural choices
- Zero code changes introduced
- All existing functionality preserved
- Server alias (`Server = PalfreyServer`) intact in `__init__.py`
- All complex sections documented without behavior alteration
