# Task 14 — Scenario 2: Rust and Python fallback semantic parity

Date: 2026-03-11

## Rust-enabled verification

Command:

```bash
task test
```

Result:

- `702 passed, 15 skipped`
- Coverage gate passed (`89.51%`)

## Fallback-only verification

Command:

```bash
PALFREY_NO_RUST=1 task test
```

Result:

- `702 passed, 15 skipped`
- Coverage gate passed (`89.54%`)

## Functional parity checks added in tests

`tests/unit/test_acceleration.py` now verifies:

1. `parse_request_head` Rust return contract is byte-oriented (`bytes`) at extension boundary.
2. `parse_header_items` common formats parse exactly as fallback.
3. `split_csv_values` edge cases (`""`, single, sparse comma forms).
4. `unmask_websocket_payload` randomized parity against fallback.
5. Randomized cross-function parity test comparing Rust path vs forced-fallback path.

## Notes

- `acceleration.parse_request_head` keeps public API unchanged (`tuple[str, str, str, list[tuple[str, str]]]`) by decoding Rust byte returns with `latin-1`, matching fallback semantics.
- `PALFREY_NO_RUST` environment gate is now supported to force fallback mode in QA.
