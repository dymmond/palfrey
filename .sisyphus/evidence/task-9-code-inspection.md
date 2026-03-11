# Task 9 Manual QA — Code Inspection for Header Encode Cycles

Inspection command:

```bash
grep "\\.encode(" palfrey/protocols/http.py
```

Findings relevant to header hot path:

- `on_header(name, value)` now appends `(name.lower(), value)` directly (bytes in, bytes stored).
- `build_http_scope(...)` now reuses bytes headers (or coerces once for mixed inputs) and does **not** call `.encode()` on header names/values.
- Remaining `.encode()` usages in `http.py` are non-header-path operations (path/query serialization, response/status framing, config header defaults, generic coercion helper).

Result: no str→bytes `.encode()` calls remain on header names/values in `on_header` + `build_http_scope` hot path.
