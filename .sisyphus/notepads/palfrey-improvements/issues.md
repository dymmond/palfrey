# Issues & Gotchas

This notepad records problems encountered, gotchas discovered, and workarounds applied.

---

## Known Issues (Pre-Work)

**LSP Type Errors** (from plan analysis):
- `server.py:223,227,295,305,469,1112` — 6 errors (None attribute access, non-awaitable objects, type mismatches)
- `protocols/websocket.py:515,577,811,1305` — 4 errors (ConvertibleToInt, _transport access, exception tuple)
- `protocols/http.py:139,346` — Optional import resolution (httptools, h11)
- `loops/uvloop.py:26,29` — Optional import resolution (uvloop)
- `config.py:18,245,265` — Optional import resolution (click, uvloop)

**Docstring Coverage** (from plan):
- Module docstrings: 9.4%
- Function docstrings: 86.3%

## Issues Discovered During Execution

_(To be populated as issues are encountered)_

## Task 8 Streaming Writer Gotchas (RESOLVED)

- Initial `_write_response` switch to `writer.writelines(...)` broke server tests using dummy writers without a `writelines` method.
- Resolution: Added runtime compatibility fallback in `_write_response`:
  - use `writelines(payload_chunks)` when callable,
  - otherwise iterate chunks and call `writer.write(chunk)`.
- This preserved production streaming behavior while keeping test doubles and custom writer implementations compatible.

---

_Updated by subagents when problems are encountered or resolved._

## E402 Fix - test_server_edge_cases.py (RESOLVED)

**Issue**: E402 (module level import not at top of file) violations in test_server_edge_cases.py

**Root Cause**: Line 7 had `pytest = __import__("pytest")` which flagged subsequent imports as E402

**Solution Implemented**:
1. Replaced `pytest = __import__("pytest")` with normal `import pytest`
2. Reorganized imports following standard order:
   - `__future__` imports
   - Standard library (asyncio, types, typing, collections.abc)
   - Third-party (pytest)
   - First-party (palfrey imports)

**Changes Made**:
- Lines 1-13 reordered
- All test logic unchanged (15 tests remain functional)
- Import structure now clean per ruff standards

**Verification**:
- Lint check: All checks passed
- Test suite: 660 passed, 11 skipped (includes 15 from test_server_edge_cases.py)
- No E402 errors

**Status**: ✅ COMPLETE

## Task 15 WebSocket Header Bytes Conversion (RESOLVED)

**Issue**: After Task 9 converted HTTP headers to bytes for zero-copy optimization, WebSocket upgrade requests needed proper header conversion in `server.py` before passing to `handle_websocket()`.

**Root Cause**:
- Task 9 keeps HTTP request headers as bytes internally (`list[tuple[bytes, bytes]]`) for performance
- WebSocket handler signature (`websocket.py:1824`) expects `headers: list[tuple[str, str]]`
- `read_http_request()` (line 379) DOES decode headers to strings for WebSocket requests, but server.py originally just cast without proper type safety

**Problem Manifestation**:
- If headers remained bytes, WebSocket protocol handler would receive wrong type
- Type checker could not guarantee headers were strings due to `Sequence` type annotation
- Defensive conversion needed at server.py handoff point

**Solution Implemented**:
- Added explicit header conversion in `server.py` lines 642-648:
  ```python
  websocket_headers = [
      (
          name.decode("latin-1") if isinstance(name, bytes) else str(name),
          value.decode("latin-1") if isinstance(value, bytes) else str(value),
      )
      for name, value in request.headers
  ]
  ```
- Defensive pattern: checks `isinstance(name, bytes)` before decoding
- Fallback to `str(name)` for already-string headers (handles both code paths)
- Replaced previous `cast("list[tuple[str, str]]", request.headers)` which had no runtime guarantee

**Type Safety Achieved**:
- `HTTPRequest.headers` is `Sequence[tuple[str, str] | tuple[bytes, bytes]]` (mixed possible)
- Conversion ensures `websocket_headers: list[tuple[str, str]]` passed to `handle_websocket()`
- Type checker now knows WebSocket receives correct types

**Verification**:
- ✅ WebSocket benchmark: 10k messages across 10 clients (20,333 ops/s)
- ✅ HTTP benchmark: 100k requests across 20 concurrent (33,367 ops/s)
- ✅ All WebSocket protocol tests pass (128 tests)
- ✅ Header bytes tests pass (4 tests confirm bytes preservation for HTTP)
- ✅ Lint clean: no new diagnostics
- ✅ No extra bytes copies in HTTP hot path (headers stay bytes)

**Performance Impact**:
- Zero-copy HTTP headers preserved (no `.encode()` calls)
- WebSocket conversion overhead negligible (~7 header copies per upgrade request, amortized <1% of connection setup)
- Trade-off: Type safety + defensive conversion vs direct cast

**Status**: ✅ COMPLETE
