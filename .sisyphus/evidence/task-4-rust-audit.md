# Task 4 — Rust Extension Audit (`palfrey-improvements`)

Date: 2026-03-11

## Scope

- `rust/palfrey_rust/src/lib.rs`
- `palfrey_rust.pyi`
- `palfrey/acceleration.py`
- Rust build attempt in `rust/` via `maturin develop`

## Build & Toolchain Status

### Tool availability

- `cargo`: **available** (`/Users/tarsil/.cargo/bin/cargo`)
- `rustc`: **available** (`/Users/tarsil/.cargo/bin/rustc`)
- `maturin`: **not available** (`maturin not found`)

### Build attempt

Command run:

```bash
maturin develop
```

Working directory:

```text
rust/
```

Result:

```text
zsh:1: command not found: maturin
```

Status: **Build not executed** because `maturin` is missing from PATH. No Rust/PyO3 compilation errors were observed yet (blocked before build start).

## Exported Rust Functions (`lib.rs`)

The `#[pymodule]` block exports exactly 4 functions:

1. `parse_header_items(headers: Vec<String>) -> PyResult<Vec<(String, String)>>`
2. `split_csv_values(value: &str) -> Vec<String>`
3. `parse_request_head(data: &[u8]) -> PyResult<(String, String, String, Vec<(String, String)>)>`
4. `unmask_websocket_payload(payload: &[u8], masking_key: &[u8]) -> PyResult<Vec<u8>>`

## Python Interface / Stub Analysis (`palfrey_rust.pyi`)

Stub signatures match the exported function set:

- `parse_header_items(headers: list[str]) -> list[tuple[str, str]]`
- `split_csv_values(value: str) -> list[str]`
- `parse_request_head(data: bytes) -> tuple[str, str, str, list[tuple[str, str]]]`
- `unmask_websocket_payload(payload: bytes | bytearray | memoryview, masking_key: bytes) -> bytes`

Notes:

- The stubs model **string-heavy** interfaces for HTTP request-line/header parsing (`str` output), not byte-preserving output.
- `unmask_websocket_payload` accepts broad Python buffer types in stubs; Rust accepts `&[u8]` so PyO3 will materialize readable byte slices.

## Integration & Fallback Behavior (`palfrey/acceleration.py`)

### Detection strategy

- On import, Python tries:

  ```python
  from palfrey_rust import ...
  ```

- If import succeeds: `HAS_RUST_EXTENSION = True`
- On `ImportError`: `HAS_RUST_EXTENSION = False`

This makes Rust acceleration **optional**; pure Python fallback always remains available.

### Function-by-function fallback

- `parse_header_items`: uses Rust if available; wraps Rust `ValueError` into `HeaderParseError`.
- `split_csv_values`: uses Rust if available, else pure-Python split/strip/filter.
- `parse_request_head`: uses Rust if available, else Python implementation that decodes with `latin-1`.
- `unmask_websocket_payload`: validates key length, uses Rust if available, else Python XOR loop over `bytearray`.

## Zero-Copy vs Copying Analysis

Search result: **no `PyBackedBytes` usage** in Rust sources.

Observed Rust argument/return types:

- `Vec<String>`, `Vec<(String, String)>`, `Vec<u8>`, and `String` are used extensively.
- Input buffers are `&[u8]` for byte arguments (good for borrowing input at Rust boundary), but output paths allocate owned Rust containers.

Implications:

- `parse_header_items`: allocates new `String`s for parsed pairs.
- `split_csv_values`: allocates `String`s for each segment.
- `parse_request_head`: decodes bytes to UTF-8 `&str`, then allocates `String` for method/target/version/headers.
- `unmask_websocket_payload`: allocates `Vec<u8>` for output (expected for transformed payload).

Conclusion: current implementation is **copying/allocating**, not a `PyBackedBytes`-style zero-copy design.

## `parse_request_head` Return-Type & Encoding Overhead Analysis

Rust signature returns:

```rust
PyResult<(String, String, String, Vec<(String, String)>)>
```

So it returns **strings**, not bytes.

Additional behavior:

- Rust uses `std::str::from_utf8(data)`.
- Error text says `"not valid UTF-8/latin-1 byte data"`, but implementation only accepts UTF-8.
- Python fallback decodes with `latin-1`, preserving raw byte mapping semantics for non-UTF8 octets.

Impact:

- Potential semantic mismatch between Rust and fallback behavior on non-UTF8 request heads.
- String outputs imply decode cost and potential encode/decode churn if downstream logic expects bytes.

## What Works vs What Needs Fixing

### Works

- Rust extension API surface is implemented for 4 targeted helper functions.
- Python integration has robust optional-extension fallback behavior.
- Error path wrapping exists for header parsing (`HeaderParseError`).

### Doesn’t work / blocked now

- Local Rust extension build via `maturin develop` cannot run because `maturin` is not installed/available.

### Needs fixing / improvement candidates (input to Task 14)

1. **Install/standardize build tooling**
   - Ensure `maturin` is present in dev/CI environments where Rust extension should build.

2. **Align request-head decoding semantics**
   - Rust path currently enforces UTF-8; Python fallback uses latin-1.
   - Choose one canonical rule and align both implementations.

3. **Reduce allocation/copy overhead in hot paths**
   - No `PyBackedBytes` currently used.
   - Evaluate byte-oriented return types for parser outputs where possible.
   - Review whether header/request-line fields truly need eager `String` allocation.

4. **Revisit `parse_request_head` output contract**
   - If performance-sensitive path benefits from bytes, consider bytes-based contract to avoid decode/encode churn.
   - If keeping `str`, ensure clear documented rationale and consistent decoding behavior.

5. **Assess `unmask_websocket_payload` buffer strategy**
   - Current output necessarily allocates transformed bytes; investigate whether caller-visible API allows reuse/in-place patterns safely.

## Recommendation Summary for Task 14 (Rust optimization)

- First unblock build pipeline (`maturin`) so performance work can be validated.
- Prioritize `parse_request_head` semantic alignment (UTF-8 vs latin-1) before micro-optimization.
- Then optimize data movement:
  - Prefer borrowed/byte-backed pathways where API permits.
  - Minimize intermediate `String`/`Vec` allocations on parsing hot paths.
- Add parity/perf tests covering:
  - Non-UTF8 header bytes
  - Large header sets
  - High-frequency WebSocket unmask workloads
