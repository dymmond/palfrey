# Task 21 Docs Build Evidence

- Date: 2026-03-17
- Command: `task build`
- Output:
```
task: [build] hatch run docs:build
ℹ Prepared 39 docs file(s) in
/Users/tarsil/Projects/github/dymmond/palfrey/docs/generated
Build started
...
+ /guides/migrating-from-uvicorn/
...
Build finished in 0.27s
✔ Docs built with Zensical ✅
```

- Verification: `ls site/guides/migrating-from-uvicorn/index.html`
- Result: `site/guides/migrating-from-uvicorn/index.html` exists.

## Fix: Verification Failure (2026-03-17)

- **Issue**: Code example files `.py` contained bash commands, causing syntax errors.
- **Action**:
    - Renamed `docs_src/migration/uvicorn_before.py` to `uvicorn_before.sh`.
    - Renamed `docs_src/migration/palfrey_after.py` to `palfrey_after.sh`.
    - Updated `docs/en/docs/guides/migrating-from-uvicorn.md` to point to `.sh` files.
- **Verification**: `task build` succeeds and output remains correct.
