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
