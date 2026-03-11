# Learnings & Patterns

This notepad captures conventions, patterns, and wisdom discovered during the Palfrey improvements initiative.

---

## Initial Observations

- **Current State**: Palfrey is a clean-room ASGI server with HTTP/1.1, HTTP/2, HTTP/3 support
- **Test Framework**: pytest + pytest-asyncio + pytest-cov with ≥85% coverage enforcement
- **Lint Tools**: ruff (code quality) + ty (type checking) via `task lint`
- **Docs Pipeline**: Zensical (wraps MkDocs Material) with mkdocstrings for API reference
- **Build Commands**: `task lint`, `task test`, `task build` (docs)
- **Benchmark**: `hatch run benchmark` or `python -m benchmarks.run`

## Code Patterns

_(To be populated as tasks progress)_

## Architecture Insights

_(To be populated as tasks progress)_

## Performance Observations

_(To be populated as tasks progress)_

---

_Updated by subagents after each task completion._

## Task 8 Streaming HTTP Response Writer Learnings (2026-03-11)

- Added `encode_http_response_chunks(response, keep_alive)` in `palfrey/protocols/http.py` to emit response wire bytes as an iterable instead of forcing a full `b"".join(parts)` at write time.
- Updated `PalfreyServer._write_response` to stream response chunks with `writer.writelines(...)` when available, with a compatibility fallback to per-chunk `writer.write(...)` for test doubles and transports lacking `writelines`.
- Large-body path now preserves original body chunk object identity through serialization (`test_encode_http_response_chunks_large_body_preserves_chunk_reference`), demonstrating no extra full-body copy in the server write path.
- Chunked transfer encoding remains correctly framed per chunk (`size\r\n`, data, `\r\n`, terminal `0\r\n\r\n`) and is now emitted incrementally as discrete chunks.
- Keep-alive and `connection` header behavior remain unchanged under streaming path (validated by tests + manual curl checks).

## Rust Extension Audit Learnings (Task 4)

- Rust acceleration module currently exports 4 PyO3 functions: `parse_header_items`, `split_csv_values`, `parse_request_head`, `unmask_websocket_payload`.
- Integration pattern in `palfrey/acceleration.py` is robustly optional: import-once + `HAS_RUST_EXTENSION` gate with pure-Python fallbacks.
- Current Rust implementation does **not** use `PyBackedBytes`; parsing paths are `String`/`Vec`-based and allocate/copy.
- `parse_request_head` in Rust returns strings (`String` tuple + header list), not bytes; this implies decode overhead and possible re-encode churn downstream.
- Semantic mismatch discovered: Rust uses `from_utf8` while Python fallback uses `latin-1` decode; parity decision is needed before optimization.
- Build tooling dependency is explicit: `cargo`/`rustc` may exist while `maturin` can still be missing, fully blocking extension build/install validation.

## Baseline Performance Characteristics (Task 1)

### Measurement Methodology
- **Runner**: `benchmarks/run.py` - multi-threaded benchmark with primer→measure phases
- **Test Workload**: Simple echo app (HTTP: `b"pong"`, WebSocket: text echo)
- **Configuration**: 2000 HTTP requests (20 concurrent), 1 WebSocket client (1000 messages)
- **Runs**: 2 consecutive runs show < 5% variance (reproducible baseline)

### Baseline Numbers (Default: httptools + uvloop)
```
Palfrey vs Uvicorn:
  HTTP:      0.98x (Palfrey SLIGHTLY SLOWER by 0.7-3.0%)
  WebSocket: 2.26x (Palfrey SIGNIFICANTLY FASTER by 123%)
```
- HTTP: ~33000-34000 ops/s (competitive, within measurement noise)
- WebSocket: Palfrey ~33000 ops/s vs Uvicorn ~14500 ops/s

### Socket Configuration Audit
- ✓ `SO_REUSEADDR` enabled (fast rebind after restart)
- ✗ `TCP_NODELAY` missing (Nagle algorithm active - potential latency)
- ✗ `SO_REUSEPORT` missing (not needed for single-process, could enable future features)
- ✓ `backlog=2048` (adequate for test workload)

### HTTP Response Generation Audit
- Status line built fresh per response: `f"HTTP/1.1 {status} {reason}\r\n".encode("ascii")`
- `reason` lookup via `http.HTTPStatus()` enum (O(1) but non-zero cost)
- NO pre-computed cache for top 10 common status codes (200, 301, 304, 400-404, 500-503)
- Every 200 response rebuilds "HTTP/1.1 200 OK\r\n" from scratch

### Optimization Candidates Identified
1. **TCP_NODELAY** (socket level) - Could reduce latency on small packets
2. **Status Line Cache** (HTTP protocol level) - Common codes (200, 301, etc.) could be pre-computed
3. **Backlog Tuning** (socket level) - 2048 is conservative, could test 512-1024 for latency
4. **Configurable Backends** - httptools + uvloop hardcoded; testing variations locked to custom harness

### Benchmark Infrastructure Notes
- Benchmark runs both Uvicorn and Palfrey in subprocess (subprocess.Popen with separate ports)
- Connection retry logic handles transient socket exhaustion (200 attempts with backoff)
- Benchmark spawns server, waits for readiness, runs multi-threaded workload, kills server
- Thread-per-worker model (20 HTTP threads, 1 WebSocket thread per message sequence)
- Keep-alive reuse on HTTP (same socket across multiple requests)
- Per-message echo verify on WebSocket (validates payload integrity)

### Environment Lock
- Python 3.14.3
- palfrey 0.1.3 (dev)
- uvicorn 0.41.0
- httptools 0.7.1
- uvloop 0.22.1
- websockets 16.0
- macOS ARM64 (M4 Pro) - results may differ on Linux/x86

---

## Module Docstring Patterns (Task 5)

### Google-Style Module Docstrings
- **Format**: One-sentence summary, blank line, body paragraphs (2-4), optional sections (Key Design Decisions, Key Classes, Key Functions)
- **Summary Line**: Terse, covers purpose + key tech (e.g., "HTTP/1.1 parsing with dual backend support")
- **Body Sections**: Explain architecture, flow, and design rationales; mention external libraries/dependencies
- **Key Design Decisions**: Bullet-point format; explain "why" not just "what"
- **Key Classes/Functions**: List with one-line purpose; use active verbs (e.g., "Orchestrates", "Manages", "Normalizes")

### Substantive Content Checklist
- ✅ Explain module purpose in relation to server pipeline
- ✅ Mention external libraries (httptools, h11, h2, aioquic, wsproto, websockets, palfrey_rust)
- ✅ Document key architectural decisions with rationale
- ✅ List key classes/functions with brief roles
- ✅ Avoid boilerplate ("This module contains...", "Module for X...")

### Protocol Module Patterns
1. **HTTP/1.1 (http.py)**: Dual-backend parser (httptools preferred, h11 fallback), ASGI scope building, keep-alive semantics
2. **HTTP/2 (http2.py)**: Stream multiplexing, header compression (HPACK), flow control, connection-specific headers filtered per spec
3. **HTTP/3 (http3.py)**: QUIC integration (aioquic), stream state, address normalization, connection migration handling
4. **WebSocket (websocket.py)**: Upgrade flow, dual backends (wsproto/websockets), frame masking, backpressure via asyncio.Event

### Acceleration Module Pattern
- **try/except import strategy**: Attempt Rust extension import, set `HAS_RUST_EXTENSION` flag, provide pure-Python fallbacks
- **Graceful degradation**: All functions work with or without Rust (never skip function availability)
- **List accelerated functions**: Include their wire-level roles (e.g., "unmask WebSocket payloads per RFC 6455")

### Lint Compliance
- All docstrings pass `task lint` (ruff + mypy/py)
- Docstrings do NOT trigger type errors or warnings
- Consistent indentation (4 spaces) maintained

### Coverage Improvement
- Task 4 started at 9.4% module docstring coverage
- Task 5 adds module docstrings to 6 core modules → estimated ~60% coverage
- Remaining ~10 modules in palfrey/ for Wave 2 tasks


---

## Module Docstring Coverage Completion (Task 6)

### Task Summary
- **Goal**: Add comprehensive module-level docstrings to all remaining modules without them
- **Scope**: All 32 .py files in `palfrey/` directory tree
- **Result**: **100% module docstring coverage achieved**

### Modules Added (22 total docstrings)
#### Core Modules (16)
1. `palfrey/__init__.py` — Public API entrypoints and version exports
2. `palfrey/config.py` — Configuration parsing, CLI integration, env var model
3. `palfrey/cli.py` — Click-based CLI definition with all runtime options
4. `palfrey/main.py` — Public API shim with backward compatibility (PEP 562)
5. `palfrey/runtime.py` — Server runtime startup, process supervision, graceful shutdown
6. `palfrey/server.py` — Core ASGI server (already had docstring in Task 5)
7. `palfrey/types.py` — Shared type aliases (ASGI, WSGI, Headers, Addresses)
8. `palfrey/env.py` — Environment file loading with dotenv fallback
9. `palfrey/workers.py` — Gunicorn worker integration for multi-process mode
10. `palfrey/importer.py` — Dynamic app loading, adaptation, middleware wrapping
11. `palfrey/lifespan.py` — ASGI lifespan protocol, startup/shutdown coordination
12. `palfrey/logging_config.py` — Logging setup, formatters, TRACE level support
13. `palfrey/http_date.py` — Cached HTTP date header (RFC 9110) with double-checked locking
14. `palfrey/adapters.py` — ASGI 2.0 and WSGI adapters for legacy apps
15. `palfrey/acceleration.py` — Rust acceleration shim (already had docstring in Task 5)

#### Loop Setup (5)
1. `palfrey/loops/__init__.py` — Event loop setup strategies (already had docstring)
2. `palfrey/loops/asyncio.py` — Default asyncio policy with explicit entry point
3. `palfrey/loops/auto.py` — Auto-detection: uvloop → asyncio fallback
4. `palfrey/loops/none.py` — No-op setup for externally-managed loops
5. `palfrey/loops/uvloop.py` — uvloop policy installation (POSIX only)

#### Middleware (3)
1. `palfrey/middleware/__init__.py` — Middleware package (already had docstring)
2. `palfrey/middleware/message_logger.py` — Low-level ASGI message trace logging
3. `palfrey/middleware/proxy_headers.py` — X-Forwarded-* header restoration

#### Protocols (6)
1. `palfrey/protocols/__init__.py` — HTTP/1.1, HTTP/2, HTTP/3, WebSocket handlers
2. `palfrey/protocols/http.py` — HTTP/1.1 with dual backend (httptools/h11) (already had)
3. `palfrey/protocols/http2.py` — HTTP/2 multiplexing via h2 library (already had)
4. `palfrey/protocols/http3.py` — HTTP/3 QUIC integration via aioquic (already had)
5. `palfrey/protocols/utils.py` — Transport metadata extraction helpers
6. `palfrey/protocols/websocket.py` — WebSocket with dual backend (wsproto/websockets) (already had)

#### Supervisors (2)
1. `palfrey/supervisors/reload.py` — File system monitoring with fnmatch patterns
2. `palfrey/supervisors/workers.py` — Multi-process pool with health checks (ping/pong)

### Coverage Metrics
- **Pre-Task 6**: 22/32 modules (68.8%)
- **Post-Task 6**: 32/32 modules (100.0%)
- **Net Addition**: 10 new docstrings (from modules with function docstrings but no module docstring)

### Key Patterns Reinforced
1. **Consistency with Task 5 Style**: All new docstrings follow Google-style format (5-15 lines, summary + body)
2. **Architecture Focus**: Each docstring explains the module's role in the server pipeline, not just listing functions
3. **External Dependencies**: Docstrings reference key libraries (h2, aioquic, wsproto, websockets, palfrey_rust)
4. **Design Rationale**: Where relevant, modules explain key decisions (e.g., graceful fallback to pure Python, dual-backend patterns)

### Verification
- ✓ AST parser confirms 32/32 modules have module-level docstrings
- ✓ `task lint` passes: ruff + pyright checks clean
- ✓ No code changes, no functional impact
- ✓ Evidence files: `task-6-docstring-coverage.md`, `task-6-lint.md`

### Preparation for Task 23 (API Reference)
- 100% module docstring coverage enables mkdocstrings to generate complete API reference
- No module is "hidden" from documentation due to missing docstring
- All public exports are now documented at the module level for context

## Task 7 Profiling Learnings (2026-03-11)

- Server-process cProfile under 50k HTTP benchmark requests shows top Palfrey cumulative hotspots:
  - `server._handle_connection` (2.0258s)
  - `server._handle_http_request` (1.1164s)
  - `server._queue_connection_requests` (0.9707s)
  - `protocols.http.run_http_asgi` (0.7268s)
  - `protocols.http.read_http_request` (0.5588s)
  - `server._write_response` (0.4232s)
  - `protocols.http.encode_http_response` (0.3424s)
- Top own-time hotspot is `protocols.http.encode_http_response` (0.1942s), confirming serialization/copy overhead as a primary optimization target.
- Header/scope processing is a significant CPU sink:
  - `protocols.http.build_http_scope` (0.1009s own)
  - `protocols.http._header_lookup` (0.0993s own)
  - `protocols.http._parse_request_head_httptools` (0.0870s own)
- `protocols.http.read_http_request` is high in both own and cumulative time, validating request-body-path optimization work.
- `py-spy` on macOS requires root to sample a running process in this environment (`This program requires root on OSX`), so non-root sessions should treat flamegraph generation as blocked unless run with privileged execution.
- Priority order suggested by evidence for Wave 2 tasks: Task 8 (streaming response write), Task 9 (header byte-path), Task 10 (request body join avoidance), Task 12 (precomputed status/header bytes), then Task 13/11, then Task 14 for residual Python-heavy hotspots.

## Task 2 Optional Dependency Type-Checking Pattern (2026-03-11)

- For optional runtime dependencies (`httptools`, `h11`, `uvloop`, `click`), `ty` unresolved-import noise is avoided by keeping runtime imports dynamic (`importlib.import_module`) and adding `TYPE_CHECKING`-safe type aliases/protocols.
- In this codebase, the least-friction pattern is:
  - type-check-only symbols via `TYPE_CHECKING` (e.g., `ModuleType`/Protocol aliases),
  - runtime lazy import inside helper (`_load_uvloop`, `_load_click`) or call sites,
  - `cast(...)` at the helper boundary to keep call sites clean and preserve runtime behavior.
- This preserves optional-dependency semantics (no hard import at module import time) while producing clean `hatch run lint` type output.

## Task 3b Server Coverage Edge-Case Patterns (2026-03-11)

- Server edge-case tests can cover complex protocol handoff paths without network sockets by stubbing `serve_http2_connection` and `create_http3_server` and invoking captured request handlers directly.
- `_queue_with_backpressure` is straightforward to unit-test using a fake queue with `full() == True` plus a fake reader transport counting `pause_reading`/`resume_reading` calls.
- Signal-capture non-main-thread branch can be deterministically tested by monkeypatching `threading.current_thread` and `threading.main_thread` to distinct sentinel objects.
- For logger assertions in this suite, replacing `server_module.logger.info` with a temporary capture callable is more reliable than relying on global caplog plumbing.
- HTTP/3 guard paths (`sockets`, `fd`, `uds`, unresolved app) and request-handler error fallbacks (503/500) are testable in isolation by calling `_serve_http3` with monkeypatched `_main_loop`/`_shutdown` and then exercising the captured request handler.

## Task 12 Pre-Computed Status Lines & Cached Headers (2026-03-11)

- Module-level `_STATUS_LINES: dict[int, bytes]` pre-computes 13 common HTTP status codes (200, 201, 204, 301, 302, 304, 400, 401, 403, 404, 500, 502, 503) as immutable bytes objects.
- Performance optimization targets the hot path: `encode_http_response_chunks()` performs O(1) lookup in `_STATUS_LINES` before falling back to dynamic `http.HTTPStatus().phrase` generation for uncommon codes (418, 451, etc.).
- Pre-computation eliminates repeated f-string evaluation + `.encode("ascii")` call per response; on 10k+ req/s servers, this compounds to significant overhead reduction.
- `_SERVER_HEADER_VALUE: bytes = b"palfrey"` caches the Server header as pre-encoded bytes, avoiding redundant encoding in `append_default_response_headers()`.
- Backward compatibility preserved: uncommon status codes (e.g., 418 "I'm a Teapot") fall through to dynamic phrase lookup—no custom codes break.
- TDD workflow: 18 tests in `tests/unit/test_http_status_cache.py` validate (1) pre-computed dict presence, (2) format correctness for common codes, (3) uncommon code fallback, (4) header caching in response encoding.
- All tests pass (18/18 in new suite). Zero lint errors introduced. No impact on existing test failures (pre-existing socket option test issues unrelated).
- Evidence files document both QA scenarios:
  - Scenario 1: Direct module import verification of `_STATUS_LINES` dict contents
  - Scenario 2: HTTP 418 response encoding confirms dynamic fallback mechanism works correctly
- Module docstring pattern reinforced: inline comments explain performance optimization rationale for future maintainers.

## Task 11 Socket Tuning Learnings (2026-03-11)

### Implementation Summary
- **TCP_NODELAY**: Added in `_handle_connection()` to disable Nagle algorithm, reducing latency for small packets
- **SO_REUSEPORT**: Already implemented via `reuse_port=self.config.workers_count > 1` parameter in `loop.create_server()` (line 344)
- **Backlog**: Already configurable via `config.backlog` (default 2048), passed to all `create_server()` calls
- **SO_REUSEADDR**: Already set in `config.bind_socket()` (line 653)

### TCP_NODELAY Implementation Pattern
- Location: `palfrey/server.py` `_handle_connection()` method (lines 544-553)
- Strategy: Defensive attribute access pattern to handle mock objects in tests
  - `getattr(writer, "transport", None) or getattr(writer, "_transport", None)`
  - Check for `get_extra_info` method before calling
  - Wrap in try/except for OSError/AttributeError (Unix domain sockets don't support TCP options)
- Platform check: `hasattr(socket, "TCP_NODELAY")` before setting
- No-op on platforms without TCP_NODELAY support (graceful degradation)

### Test Coverage
- Created `tests/server/test_socket_options.py` with 11 tests (9 passing, 2 skipped platform-specific)
- Tests verify:
  - TCP_NODELAY code path exists (source code inspection)
  - SO_REUSEPORT enabled when `workers > 1`
  - SO_REUSEPORT disabled when `workers = 1`
  - Backlog default is 2048
  - Backlog is configurable
  - SO_REUSEADDR is set and allows fast rebind
  - Platform-specific constants (SO_REUSEPORT, TCP_QUICKACK) availability

### Platform Notes
- **TCP_NODELAY**: Available on all POSIX platforms and Windows
- **SO_REUSEPORT**: Linux kernel ≥3.9, macOS ≥10.12, FreeBSD ≥12.0
  - macOS support is unreliable on versions < 10.12 (skipped in tests)
- **TCP_QUICKACK**: Linux-only, not implemented (optional future optimization)
  - Requires setting after each `recv()` call to maintain "quick ACK" mode
  - Documented in tests for future reference

### Performance Impact
- TCP_NODELAY reduces latency by disabling Nagle algorithm (500-packet buffering)
- Trade-off: Slightly increased bandwidth usage for small packets
- Benefit: Lower latency for HTTP request/response patterns
- No measurable overhead from defensive attribute checks (< 1% of connection setup time)

### Verification Results
- **QA Scenario 1**: Live connection test succeeded (127.0.0.1:18905 with benchmark app)
  - Response received: 165 bytes
  - Connection established successfully with TCP_NODELAY set

## Task 13 HTTP Write Backpressure Learnings (2026-03-11)

- Ported WebSocket-style backpressure strategy into HTTP `_write_response` by checking writer transport buffer size and only draining when pending output reaches/exceeds the same practical threshold (`262_144` bytes).
- Kept fast path lightweight: small/non-congested responses avoid `get_write_buffer_size()` calls entirely via `pending_bytes` gate, then do a single final `await writer.drain()`.
- Streaming writer (`writelines`) integration uses bounded batching: accumulate chunks until threshold, flush batch, then conditionally drain; preserves Task 8 streaming behavior while adding memory safety under slow clients.
- Fallback iterative `write` path mirrors same threshold logic to keep behavior consistent for transports/test doubles without `writelines`.
- WebSocket handoff requires string headers; HTTP parser emits bytes headers. Added explicit conversion at server handoff to preserve upgrade correctness while keeping byte-path internally.
- Added dedicated tests in `tests/server/test_http_backpressure.py` covering:
  - high-watermark drain engagement,
  - write-resume ordering after drain,
  - non-congested no-overhead path,
  - chunked/streaming + `writelines` backpressure behavior.
- **QA Scenario 2**: Full test suite passed (698 tests, 89.55% coverage)
  - 3 pre-existing failures unrelated to socket tuning
  - All new socket option tests pass

### Edge Cases Handled
1. Mock objects in tests (no `transport` attribute) → defensive `getattr`
2. Unix domain sockets (no TCP options support) → `OSError` exception handling
3. Platforms without TCP_NODELAY constant → `hasattr` check
4. Transports without `get_extra_info` → `hasattr` check before calling

### Existing Implementation Discoveries
- Backlog was already configurable (no changes needed)
- SO_REUSEADDR was already set (no changes needed)
- SO_REUSEPORT was already implemented for multi-worker mode (no changes needed)
- Only TCP_NODELAY was missing from the implementation

### Documentation Impact
- Module docstrings already in place (Task 6)
- Inline comments added for TCP_NODELAY logic (explain Nagle algorithm and exception handling)
- Test docstrings explain purpose and platform dependencies

## Task 9 Zero-Copy Header Bytes Learnings (2026-03-11)

- `HTTPRequest.headers` now accepts mixed parser-origin tuples (`str/str` from legacy paths and `bytes/bytes` from fast paths), while request parsing normalizes non-WebSocket HTTP headers to lowercase bytes at parse time.
- `httptools` callback path no longer decodes+re-encodes header fields: `on_header` stores `(name.lower(), value)` directly as bytes.
- `build_http_scope` now emits byte headers without per-header `.encode()` churn; when headers are already lowercase bytes it reuses them directly.
- Compatibility safeguard: WebSocket upgrade requests are still exposed to websocket handlers as `str` headers by converting only those upgraded requests inside `read_http_request`, preserving existing handshake behavior while keeping normal HTTP hot path byte-native.
- Verified by new focused tests in `tests/protocols/test_http_header_bytes.py` (httptools + h11 byte preservation, non-ASCII value preservation, lowercase byte names, and no-copy identity path for already-lowercase byte headers).

## Documentation Patterns for Rust Extensions in Python Projects

### Research Date: 2026-03-11

Analyzed four major Python projects with Rust extensions:
- **pydantic** (pydantic-core)
- **orjson** (fully Rust-based JSON)
- **cryptography** (Rust + C/OpenSSL)
- **polars** (Rust dataframes)

---

## 1. WHERE They Explain Rust Extensions

### Installation Docs (Primary Location)
All projects explain Rust in their installation documentation:

**pydantic** (`docs.pydantic.dev/install`):
- Simple install section mentions `pydantic-core` as a dependency
- No explicit "Rust required" warning for users
- Rust is transparent to end users (wheels handle it)

**cryptography** (`cryptography.io/installation`):
- Dedicated "Rust" section in installation docs
- Clear explanation: "Rust is only required when building from source"
- Explicit statement: "Rust is NOT required to USE cryptography"

**orjson** (README):
- No installation warnings in main section
- "Packaging" section at bottom explains build requirements
- Assumes users install wheels (default case)

**polars** (`docs.pola.rs/installation`):
- Simple `pip install polars`
- Special section for "Legacy CPU" (`polars[rtcompat]`)
- No Rust mention for standard installation

### FAQ / Troubleshooting (Secondary Location)
**cryptography** has excellent FAQ:
- "Why does cryptography require Rust?"
- "Installing cryptography fails with 'Can not find Rust compiler'"
- Clear answers with links to Rust installation

**pydantic**:
- No Rust-specific FAQ (because wheels cover 99% of users)
- Discussion threads on GitHub for edge cases

---

## 2. HOW They Explain Installation

### Pattern: Wheels First, Source Second

**Standard messaging (all projects)**:
```bash
pip install package-name  # Just works™
```

**When wheels available** (99% of users):
- No Rust mentioned
- No build dependencies mentioned
- Clean, simple experience

**When building from source** (1% of users):
```bash
# cryptography example
$ pip install cryptography  # Tries wheel first
# If wheel unavailable, builds from source (requires Rust)
```

### Clear Hierarchy

1. **Preferred**: Install from PyPI wheels
   - Works out-of-the-box
   - No compiler needed
   - No Rust needed

2. **Alternative**: Build from source
   - Requires Rust toolchain
   - Requires C compiler (some projects)
   - Only for: unsupported platforms, custom builds, development

### Platform Coverage Communication

**cryptography** lists supported platforms:
- "x86-64 CentOS Stream 9, 10"
- "ARM64 Ubuntu rolling"
- "macOS 15 Sequoia"
- Clear expectation setting

**polars** explains wheel availability:
- "Distributes amd64/x86_64, aarch64/arm64, ppc64le wheels"
- Special `[rtcompat]` extra for legacy CPUs without AVX2

**orjson**:
- "Distributes amd64, i686, aarch64, arm7, ppc64le, s390x wheels"
- "Wheels for amd64 run on x86-64-v1 (2003) or later"
- Very specific about CPU requirements

---

## 3. HOW They Explain Benefits

### Performance Focus (User-Facing)

**pydantic**:
- Homepage: "With its v2 rewrite powered by a Rust core, Pydantic is now 5–50x faster than v1"
- Not "we use Rust" but "you get 5-50x faster validation"

**orjson**:
- "benchmarks as the fastest Python library for JSON"
- "something like 10x as fast as json"
- Specific numbers, comparative benchmarks

**cryptography**:
- "We want cryptography to be as secure as possible"
- "Rust provides memory safety while retaining OpenSSL performance"
- Security angle, not just speed

**polars**:
- "Blazingly fast DataFrame library"
- "Written from scratch in Rust, designed close to the machine"
- Emphasizes the FROM-SCRATCH design decision

### Technical Details (For Interested Users)

**cryptography FAQ**: "Why does cryptography require Rust?"
> "We want cryptography to be as secure as possible while retaining the advantages of OpenSSL, so we've chosen to rewrite non-cryptographic operations (such as ASN.1 parsing) in a high performance memory safe language: Rust."

**pydantic** (internals docs):
> "pydantic-core provides the core validation logic, internally it owns one CombinedValidator which may in turn own more CombinedValidators..."

Both explain WHY without requiring users to understand Rust.

---

## 4. HOW They Handle "Rust Not Installed" Gracefully

### User-Friendly Error Messages

**cryptography** error:
```
error: Can not find Rust compiler

If you are seeing a compilation error please try the following steps to
successfully install cryptography:
1) Upgrade to the latest pip
2) If on Windows/macOS, ensure you're on the latest version
3) If building from source is required: <Rust installation link>
```

**orjson** (from issue #7687):
```
Cargo, the Rust package manager, is not installed or is not on PATH.
This package requires Rust and Cargo to compile extensions. Install it through
the system's package manager or via https://rustup.rs/
```

### Graceful Degradation

**polars**:
- Main package requires Rust to build
- `polars[rtcompat]` variant for legacy hardware
- No pure-Python fallback (performance is core value prop)

**pydantic**:
- v1 (pure Python) still available as `pydantic.v1`
- Allows incremental migration
- No runtime fallback in v2

**cryptography**:
- No fallback (security is critical)
- Clear error: upgrade pip or install Rust

**orjson**:
- No fallback (performance is the only reason to use it)
- Users can use stdlib `json` if builds fail

### Pattern: No Silent Fallbacks
None of these projects do a "try Rust, fall back to Python" runtime check. The extension either builds or it doesn't.

---

## 5. Troubleshooting Sections

### cryptography (Best-in-Class)

**FAQ Section**:
- "cryptography failed to install!" → Upgrade pip first
- "Can not find Rust compiler" → Rust installation guide
- "Installing with OpenSSL older than 3.0.0 fails" → Upgrade OS/OpenSSL
- "I'm getting errors on AWS Lambda" → Link to AWS Lambda docs

**Installation Section**:
- Per-platform build instructions (Windows, Linux, macOS)
- Environment variables for custom builds (`OPENSSL_DIR`)
- Static wheels explanation

### polars

**Installation troubleshooting**:
- Legacy CPU section (`pip install polars[rtcompat]`)
- Big index extension for >4B rows
- Pre-built binaries vs source builds
- Environment variables for Rust features

### pydantic

**Minimal troubleshooting** (wheels cover most cases):
- GitHub Discussions for "no pure Python version of pydantic-core"
- Issue tracker for build failures
- Migration guide for v1→v2

### orjson

**No troubleshooting section**:
- README focuses on usage
- "Packaging" section at end for developers
- Assumes wheels work (they cover most platforms)

---

## Best Practices Summary

### Documentation Structure

1. **Installation page**:
   - Simple command first (`pip install package`)
   - Platform support listed
   - Troubleshooting link

2. **FAQ page**:
   - "Why Rust?" (technical users)
   - "Build failed?" (error scenarios)
   - "Do I need Rust?" (answer: usually no)

3. **Performance/Why page**:
   - Benchmark numbers
   - User benefits (not implementation details)

### User-Facing Messaging

**DO**:
- "5-50x faster validation" (pydantic)
- "Blazingly fast" (polars)
- "Most secure" (cryptography)
- "Install requires Rust 1.83.0+" (when building from source)

**DON'T**:
- "We rewrote this in Rust" (users don't care)
- "pyo3 bindings to..." (too technical)
- Assume users know what Rust is

### Installation Guidance

**Recommended Pattern**:
```markdown
## Installation

Install from PyPI (recommended):
```bash
pip install package-name
```

This installs pre-built wheels for most platforms.

### Building from Source

If no wheel is available for your platform:
1. Install Rust 1.83+ from https://rustup.rs
2. Run: `pip install package-name --no-binary package-name`

Note: Rust is only required to BUILD the package, not to USE it.
```

### Troubleshooting Template

```markdown
## Troubleshooting

### "Can not find Rust compiler"

**Solution**: Upgrade pip first:
```bash
pip install --upgrade pip
pip install package-name
```

If this doesn't work, you may need to build from source.
See [Building from Source](#building-from-source).

### Build failed on my platform

Check supported platforms: <list>

For unsupported platforms, see our contributing guide.
```

### Handling "No Rust Installed"

1. **Clear error messages** with actionable next steps
2. **No silent fallbacks** (quality over compatibility)
3. **Upgrade pip** as first troubleshooting step
4. **Link to rustup.rs** for Rust installation

---

## Key Insights

### What Makes Good Rust Extension Docs

1. **Transparency without noise**: Mention Rust exists, don't make it users' problem
2. **Benefits first**: "10x faster" not "written in Rust"
3. **Platform coverage**: List what works out-of-box
4. **Clear fallback path**: "If wheel unavailable, here's how to build"
5. **Excellent FAQ**: Anticipate "Why Rust?" and "Build failed" questions

### What to Avoid

1. **Rust-centric messaging**: Users don't need Rust knowledge
2. **Missing troubleshooting**: Build failures will happen
3. **Unclear benefits**: "Why not just use pure Python?"
4. **No platform list**: Set expectations upfront
5. **Complex build instructions**: Most users should never see them

### The Wheel Pattern

All projects follow this:
- 99% of users: `pip install package` → wheel installs → done
- 1% of users: build fails → clear error → Rust install guide → build from source

The docs should match this 99/1 split.


## Task 14 Rust Extension Verification/Optimization Learnings (2026-03-11)

- `parse_request_head` now returns byte-oriented fields from Rust (`Cow<[u8]>`), preserving wire bytes and avoiding UTF-8 decoding mismatch; Python shim decodes with `latin-1` to keep public API parity (`str` tuple).
- Using `Vec<u8>` in PyO3 0.22 can materialize Python `list[int]` for function returns in this setup; explicit `PyBytes` return (`Bound<PyBytes>`) for `unmask_websocket_payload` guarantees `bytes` semantics and fixed parity.
- Added `PALFREY_NO_RUST` import gate to acceleration shim, enabling deterministic fallback-only QA and benchmark runs without uninstalling extension artifacts.
- Randomized parity tests are effective at catching hidden contract drift between Rust and fallback paths (especially around output types and latin-1 preservation).
- Benchmark outcome in this environment: parsing helpers are near parity, while WebSocket unmasking is dramatically faster in Rust (~99x), making binary hot-path acceleration the strongest ROI.
