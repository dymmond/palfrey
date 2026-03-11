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
