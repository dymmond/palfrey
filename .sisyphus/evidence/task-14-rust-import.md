# Task 14 — Scenario 1: Rust extension builds and imports

Date: 2026-03-11

## Build

Command:

```bash
hatch run rust-build
```

Result excerpt:

```text
🔗 Found pyo3 bindings
🐍 Found CPython 3.13 ...
Compiling palfrey_rust v0.3.0 (.../rust/palfrey_rust)
Finished `release` profile [optimized]
📦 Built wheel .../palfrey_rust-0.3.0-cp313-...whl
🛠 Installed palfrey_rust-0.3.0
```

## Import verification

Command:

```bash
hatch run python -c "import palfrey_rust; print(sorted([name for name in dir(palfrey_rust) if not name.startswith('__')]))"
```

Output:

```text
['palfrey_rust', 'parse_header_items', 'parse_request_head', 'split_csv_values', 'unmask_websocket_payload']
```

## Function import verification

Command:

```bash
hatch run python -c "from palfrey_rust import parse_request_head, parse_header_items, split_csv_values, unmask_websocket_payload; print('All functions available')"
```

Output:

```text
All functions available
```
