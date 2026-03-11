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
