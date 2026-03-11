# Palfrey Major Improvement Initiative

## TL;DR

> **Quick Summary**: Systematically improve Palfrey across 4 pillars: fix bugs/code smells via agent-driven audit, significantly boost HTTP performance through profiling-driven optimizations (streaming writes, zero-copy buffers, header byte-path, Rust extension, socket tuning), overhaul documentation to be best-in-class with comprehensive examples and explanations, and achieve near-100% docstring coverage.
>
> **Deliverables**:
> - All LSP type errors and code smells fixed, passing `ruff`, `ty`, and `task lint`
> - Measurably faster HTTP performance (profiling-guided, targeting significant improvement over current baseline)
> - Documentation expanded with migration guide, architecture deep-dive, API reference, k8s examples, reproducible benchmarks
> - Module docstrings from 9.4% → 100%, function docstrings from 86% → 95%+
> - All existing tests pass + new tests for every change (TDD workflow)
>
> **Estimated Effort**: XL
> **Parallel Execution**: YES — 6 waves
> **Critical Path**: Baseline profiling → Core performance optimizations → Integration verification → Documentation

---

## Context

### Original Request
User wants to take Palfrey to the next level:
1. Close bugs, gaps, and code smells
2. Performance boost — HTTP should be significantly faster than current baseline
3. Improve documentation exponentially — add missing bits, expand explanations, add examples
4. Improve docstrings of the codebase

Additional constraints: all tests must pass, add new and missing tests, use hatch/ruff/ty/Taskfile.

### Interview Summary
**Key Discussions**:
- Target platform: Same compatibility as uvicorn (Linux, macOS, Windows)
- Native extensions: Welcome — Rust, C, Cython — whatever gets best performance
- Protocol scope: HTTP/1.1, HTTP/2, HTTP/3 all in scope
- Documentation audience: Both framework authors/advanced users AND application developers
- Test strategy: TDD (tests first) — RED → GREEN → REFACTOR
- Performance target: Significant flexible improvement, profiling-driven, not locked to specific multiplier
- Rust extension: Status unknown — user is not a Rust developer. Must work transparently.
- Bugs/smells: Agent-driven audit to find and fix systematically

**Research Findings**:
- Palfrey architecture: Pure Python core + optional Rust (PyO3), httptools (C), uvloop (Cython)
- Core files: server.py (connection lifecycle), protocols/http.py (parsing/ASGI/serialization), acceleration.py (Rust shim)
- Key bottlenecks identified: encode_http_response b"".join copies entire body, header str↔bytes decode/encode cycles, chunked framing in memory, unconditional body join
- 6+ LSP type errors across server.py, websocket.py, loops/uvloop.py
- Module docstrings: 9.4%, function docstrings: 86.3%, class docstrings: 97.1%
- Zensical (wraps MkDocs with material theme) as docs build tool, with mkdocstrings + mkdocstrings-python already in deps but no auto-generated API reference. Docs pipeline: source in `docs/en/docs/` → `prepare_docs_tree()` expands includes → `docs/generated/` → `zensical build`. Build command: `task build`.
- Test coverage ≥85% enforced via pytest-cov

### Metis Review
**Identified Gaps** (addressed):
- Benchmark methodology: Current benchmarks need validation against 3-phase approach (primer→warmup→measure)
- Pre-computed status lines: Quick performance win — verify if Palfrey does this
- Backpressure in HTTP writes: WebSocket path has backpressure-aware drain but HTTP _write_response doesn't
- Rust extension: Check if it uses PyBackedBytes or copies via Vec<u8>
- Socket tuning: Verify TCP_NODELAY, SO_REUSEPORT, backlog ≥2048 are set/tunable
- Free-threading: NOT ready for ASGI servers — excluded from scope
- Custom memory allocators: Not without profiling evidence — excluded
- HTTP/3 optimization: Marginal gains for complexity — deprioritized (correctness only, not performance)

---

## Work Objectives

### Core Objective
Make Palfrey a best-in-class ASGI server with measurably superior performance, rock-solid code quality, and documentation that sets the standard for Python server projects.

### Concrete Deliverables
- Zero LSP type errors across all core modules
- `task lint` (ruff + ty) passes cleanly
- All existing tests pass + new TDD tests for every change
- Profiling report identifying top CPU/allocation hotspots
- Streaming HTTP response writer (no full-body b"".join)
- Zero-copy header handling (bytes throughout hot path)
- Rust extension verified, documented, and optimized
- Socket tuning (TCP_NODELAY, SO_REUSEPORT, tunable backlog)
- Before/after benchmark comparison showing improvement
- Module docstrings on 100% of palfrey/* modules
- Function docstrings on 95%+ of functions
- New docs pages: migration guide, architecture deep-dive, API reference, k8s examples, benchmark playbook
- Expanded existing docs with more examples and explanations

### Definition of Done
- [ ] `task lint` passes (ruff + ty check)
- [ ] `task test` passes (all tests, coverage ≥85%)
- [ ] `hatch run benchmark` shows measurable HTTP improvement over baseline
- [ ] Zero LSP type errors in core modules
- [ ] Documentation site builds cleanly (`task build`)
- [ ] Module docstring coverage = 100%
- [ ] Function docstring coverage ≥ 95%

### Must Have
- All existing tests continue to pass
- TDD workflow: tests written before implementation
- All changes pass `ruff check` and `ty check`
- Benchmark baseline captured BEFORE any performance changes
- Each performance optimization individually benchmarked
- Documentation builds without errors
- Backward-compatible changes (no public API breaks)

### Must NOT Have (Guardrails)
- No free-threading optimizations (Python 3.13+ nogil — not ready for ASGI)
- No custom memory allocators without profiling evidence
- No HTTP/3 performance optimization (correctness only, not perf tuning)
- No public API/CLI breaking changes
- No hardcoded platform-specific code without cross-platform fallback
- No `as any`/`# type: ignore` without explanatory comment
- No removal of existing tests
- No docstring boilerplate — every docstring must explain WHY, not just WHAT
- No documentation that requires Rust knowledge from users
- No premature Cython — profile first, optimize targeted hot paths only
- No excessive abstraction in hot paths — keep code direct and measurable

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: TDD (tests first)
- **Framework**: pytest + pytest-asyncio + pytest-cov
- **Test commands**: `task test` (runs `hatch run test:test`)
- **Coverage floor**: 85% (enforced by --cov-fail-under=85)
- **Lint commands**: `task lint` (runs `hatch run lint` + `hatch run check-types`)
- **Each task**: RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Code changes**: Run `task lint` + `task test` — capture output
- **Performance changes**: Run `hatch run benchmark` — capture before/after ops/s
- **Documentation**: Run `task build` — verify site builds without errors
- **Docstrings**: Run AST scan script or grep to verify coverage metrics

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — baseline + audit + scaffolding):
├── Task 1: Capture performance baseline [quick]
├── Task 2: Audit & fix LSP type errors and code smells [deep]
├── Task 3: Audit & fix missing tests / test gaps [deep]
├── Task 4: Audit Rust extension status and document findings [deep]
├── Task 5: Module docstrings — core modules (server, protocols, acceleration) [quick]
├── Task 6: Module docstrings — supporting modules (loops, middleware, adapters, etc.) [quick]
└── Task 7: Profile HTTP hot paths with py-spy/cProfile [deep]

Wave 2 (Core Performance — MAX PARALLEL, after Wave 1):
├── Task 8: Streaming HTTP response writer (depends: 1, 7) [deep]
├── Task 9: Zero-copy header handling — keep bytes in hot path (depends: 7) [deep]
├── Task 10: Eliminate unconditional body b"".join (depends: 7) [deep]
├── Task 11: Socket tuning — TCP_NODELAY, SO_REUSEPORT, backlog (depends: 1) [unspecified-high]
├── Task 12: Pre-computed status lines + cached headers (depends: 7) [quick]
├── Task 13: HTTP write backpressure (port from WebSocket path) (depends: 7) [unspecified-high]
└── Task 14: Rust extension — verify, fix, optimize (depends: 4) [deep]

Wave 3 (Performance Integration + Advanced, after Wave 2):
├── Task 15: Benchmark each optimization individually (depends: 8-14) [deep]
├── Task 16: HTTP/2 streaming response optimization (depends: 8) [unspecified-high]
├── Task 17: Benchmark methodology upgrade — 3-phase approach (depends: 15) [unspecified-high]
├── Task 18: Function docstrings — protocols/ (http.py, websocket.py, http2.py, http3.py) [unspecified-high]
├── Task 19: Function docstrings — server.py, config.py, remaining modules [unspecified-high]
└── Task 20: Inline code comments for complex algorithms [unspecified-high]

Wave 4 (Documentation Overhaul — after Waves 1-3):
├── Task 21: Documentation — Uvicorn migration guide [writing]
├── Task 22: Documentation — Architecture deep-dive & internals [writing]
├── Task 23: Documentation — Auto-generated API reference (mkdocstrings) [unspecified-high]
├── Task 24: Documentation — Kubernetes/Helm deployment examples [writing]
├── Task 25: Documentation — Reproducible benchmark playbook [writing]
├── Task 26: Documentation — Custom protocol tutorial [writing]
└── Task 27: Documentation — Expand existing pages with examples [writing]

Wave 5 (Integration & Polish, after Wave 4):
├── Task 28: Full test suite pass + coverage verification [deep]
├── Task 29: Final lint/type check clean pass [quick]
├── Task 30: Final benchmark comparison — before vs after [deep]
└── Task 31: Documentation site build verification [quick]

Wave FINAL (Verification — 4 parallel reviewers):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 7 → Task 8 → Task 15 → Task 30 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 7 (Waves 1 & 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 8, 11, 15, 30 | 1 |
| 2 | — | 28, 29 | 1 |
| 3 | — | 28 | 1 |
| 4 | — | 14 | 1 |
| 5 | — | 18, 19, 23 | 1 |
| 6 | — | 18, 19, 23 | 1 |
| 7 | — | 8, 9, 10, 12, 13 | 1 |
| 8 | 1, 7 | 15, 16 | 2 |
| 9 | 7 | 15 | 2 |
| 10 | 7 | 15 | 2 |
| 11 | 1 | 15 | 2 |
| 12 | 7 | 15 | 2 |
| 13 | 7 | 15 | 2 |
| 14 | 4 | 15 | 2 |
| 15 | 8-14 | 17, 30 | 3 |
| 16 | 8 | 28 | 3 |
| 17 | 15 | 30 | 3 |
| 18 | 5, 6 | 23 | 3 |
| 19 | 5, 6 | 23 | 3 |
| 20 | — | 22 | 3 |
| 21 | — | 31 | 4 |
| 22 | 20 | 31 | 4 |
| 23 | 18, 19 | 31 | 4 |
| 24 | — | 31 | 4 |
| 25 | 17 | 31 | 4 |
| 26 | — | 31 | 4 |
| 27 | — | 31 | 4 |
| 28 | 2, 3, 16 | F1-F4 | 5 |
| 29 | 2 | F1-F4 | 5 |
| 30 | 15, 17 | F1-F4 | 5 |
| 31 | 21-27 | F1-F4 | 5 |

### Agent Dispatch Summary

- **Wave 1**: **7 tasks** — T1→`quick`, T2→`deep`, T3→`deep`, T4→`deep`, T5→`quick`, T6→`quick`, T7→`deep`
- **Wave 2**: **7 tasks** — T8→`deep`, T9→`deep`, T10→`deep`, T11→`unspecified-high`, T12→`quick`, T13→`unspecified-high`, T14→`deep`
- **Wave 3**: **6 tasks** — T15→`deep`, T16→`unspecified-high`, T17→`unspecified-high`, T18→`unspecified-high`, T19→`unspecified-high`, T20→`unspecified-high`
- **Wave 4**: **7 tasks** — T21→`writing`, T22→`writing`, T23→`unspecified-high`, T24→`writing`, T25→`writing`, T26→`writing`, T27→`writing`
- **Wave 5**: **4 tasks** — T28→`deep`, T29→`quick`, T30→`deep`, T31→`quick`
- **Wave FINAL**: **4 tasks** — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [x] 1. Capture Performance Baseline

  **What to do**:
  - Run `hatch run benchmark` with default settings and capture output (HTTP + WebSocket ops/s)
  - Run with variations: `--http httptools --loop uvloop` vs `--loop asyncio` vs no httptools
  - Record results in `.sisyphus/evidence/task-1-baseline.md` as structured table
  - Verify benchmark methodology: check if benchmarks/run.py uses primer→warmup→measure phases
  - Record Python version, OS, CPU, and package versions for reproducibility
  - Check current socket options: search server.py for TCP_NODELAY, SO_REUSEPORT, backlog settings
  - Check if pre-computed status lines exist (search for status line caching in http.py)

  **Must NOT do**:
  - Do not modify any code — this is measurement only
  - Do not install new dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Running existing benchmark commands and recording output — no code changes
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None needed for benchmark execution

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5, 6, 7)
  - **Blocks**: Tasks 8, 11, 15, 30
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — The benchmark runner. Read it to understand methodology, what scenarios are tested, how ops/s is measured
  - `benchmarks/apps.py` — The ASGI apps used for benchmarking. Understand what workload is being measured

  **API/Type References**:
  - `pyproject.toml:124` — `benchmark = "python -m benchmarks.run"` — the hatch script entry

  **External References**:
  - Granian benchmark methodology: 3-phase (4s primer, 3s warmup, 10s measure) — compare to current approach

  **WHY Each Reference Matters**:
  - benchmarks/run.py: Need to understand what the benchmark measures to know if results are meaningful
  - benchmarks/apps.py: The test app determines what's being benchmarked (simple echo vs complex routing)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Baseline benchmark capture
    Tool: Bash
    Preconditions: hatch environment set up, uvicorn installed (benchmark extra)
    Steps:
      1. Run: hatch run benchmark --http-requests 100000
      2. Capture HTTP ops/s and WebSocket ops/s from output
      3. Run again with: hatch run benchmark --http-requests 100000 (verify consistency ±5%)
      4. Save results to .sisyphus/evidence/task-1-baseline.md
    Expected Result: Baseline numbers captured in evidence file with env metadata
    Failure Indicators: Benchmark fails to run, or results vary >10% between runs
    Evidence: .sisyphus/evidence/task-1-baseline.md

  Scenario: Socket and optimization audit
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. Search server.py for TCP_NODELAY, SO_REUSEPORT, setsockopt
      2. Search http.py for STATUS_LINE, status_line cache, pre-computed
      3. Search server.py for backlog setting
      4. Record findings in evidence file
    Expected Result: Clear list of which optimizations exist vs missing
    Evidence: .sisyphus/evidence/task-1-socket-audit.md
  ```

  **Commit**: NO (measurement only, no code changes)

- [x] 2. Audit & Fix LSP Type Errors and Code Smells

  **What to do**:
  - Fix all known LSP type errors (TDD: write tests first that exercise the affected code paths):
    - `server.py`: 6 errors — None attribute access on lifespan (lines 223, 227), non-awaitable objects (lines 295, 305, 469), _servers type mismatch (line 1112)
    - `protocols/websocket.py`: 4 errors — ConvertibleToInt type issues (lines 515, 577), _transport attribute access (line 811), invalid exception class tuple (line 1305)
    - `protocols/http.py`: Import resolution for optional deps httptools/h11 — add proper TYPE_CHECKING guards
    - `loops/uvloop.py`: Import resolution for optional dep uvloop — add TYPE_CHECKING guard
    - `config.py`: Import resolution for click/uvloop — add TYPE_CHECKING guards
  - Run `task lint` (ruff + ty) and fix all issues
  - Scan for additional code smells: unused imports, empty except blocks, bare except, print statements in production code, commented-out code
  - Fix all findings while maintaining backward compatibility

  **Must NOT do**:
  - Do not change public API signatures
  - Do not add `# type: ignore` without explanatory comment
  - Do not remove existing test coverage

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding type system, ASGI protocol semantics, and conditional import patterns for optional dependencies
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5, 6, 7)
  - **Blocks**: Tasks 28, 29
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `palfrey/server.py:223,227,295,305,469,1112` — Lines with type errors. Read surrounding context to understand the correct types
  - `palfrey/protocols/websocket.py:515,577,811,1305` — Lines with type errors
  - `palfrey/protocols/http.py:139,346` — Optional import pattern needed
  - `palfrey/loops/uvloop.py:26,29` — Optional import pattern needed

  **API/Type References**:
  - `palfrey/types.py` — Project type aliases; understand what ASGI types are defined
  - `pyproject.toml:148-155` — Ruff config (line-length 100, target py310, select rules)
  - `pyproject.toml:160-161` — ty config (currently commented out)

  **Test References**:
  - `tests/unit/test_acceleration.py` — Example of testing optional dependency code paths
  - `tests/protocols/test_http_parser.py` — Tests for HTTP parser (verify fixes don't break)
  - `tests/server/test_server_internal.py` — Server internal tests

  **WHY Each Reference Matters**:
  - Type errors at specific lines: These ARE the bugs to fix — read surrounding code to understand correct fix
  - types.py: Defines project-wide type aliases that fixes should use
  - Ruff/ty config: All fixes must pass these linters

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests written for affected code paths BEFORE fixes
  - [ ] `task lint` passes (ruff + ty) with zero errors
  - [ ] `task test` passes with ≥85% coverage
  - [ ] Zero LSP type errors in server.py, websocket.py, http.py, uvloop.py, config.py

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All type errors resolved
    Tool: Bash
    Preconditions: None
    Steps:
      1. Run: hatch run check-types
      2. Run: hatch run lint
      3. Verify output shows zero errors
    Expected Result: Both commands exit 0 with no error output
    Failure Indicators: Any remaining type errors or lint warnings
    Evidence: .sisyphus/evidence/task-2-lint-clean.md

  Scenario: No regressions in existing tests
    Tool: Bash
    Preconditions: None
    Steps:
      1. Run: task test
      2. Verify all tests pass and coverage ≥85%
    Expected Result: All tests pass, coverage report shows ≥85%
    Failure Indicators: Any test failure or coverage drop below 85%
    Evidence: .sisyphus/evidence/task-2-test-pass.md
  ```

  **Commit**: YES
  - Message: `fix: resolve type errors and code smells across core modules`
  - Files: `palfrey/server.py`, `palfrey/protocols/websocket.py`, `palfrey/protocols/http.py`, `palfrey/loops/uvloop.py`, `palfrey/config.py`, `tests/`
  - Pre-commit: `task lint && task test`

- [x] 3. Audit & Fix Missing Tests / Test Gaps

  **What to do**:
  - Run `task test` and review coverage report to identify modules/functions below 85%
  - Identify untested code paths in critical modules:
    - `palfrey/acceleration.py` — Test both Rust-enabled and Python-fallback paths
    - `palfrey/protocols/http.py` — Test all parser backends (httptools, h11, Rust), chunked encoding, keep-alive decisions
    - `palfrey/protocols/http2.py` — Verify HTTP/2 stream handling has test coverage
    - `palfrey/protocols/http3.py` — Verify HTTP/3 QUIC handling has test coverage
    - `palfrey/server.py` — Test backpressure, pipelining queue, concurrency limiting, graceful shutdown
  - Write new tests for identified gaps using TDD workflow
  - Ensure edge cases are covered: empty bodies, huge headers, malformed requests, connection drops

  **Must NOT do**:
  - Do not modify production code in this task — test-only changes
  - Do not add tests that are flaky/timing-dependent without proper asyncio handling

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding ASGI protocol semantics, async testing patterns, and coverage analysis
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5, 6, 7)
  - **Blocks**: Task 28
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `tests/protocols/test_http_parser.py` — Existing HTTP parser test patterns to follow
  - `tests/protocols/test_http_asgi.py` — ASGI test patterns
  - `tests/server/test_server_internal.py` — Server internal test patterns
  - `tests/unit/test_acceleration.py` — Acceleration/optional-dep test patterns
  - `tests/conftest.py` — Shared fixtures and test configuration

  **API/Type References**:
  - `pyproject.toml:163-177` — Pytest configuration, markers, coverage settings

  **WHY Each Reference Matters**:
  - Existing test files: Follow established patterns for consistency — fixture usage, assertion style, async test setup
  - conftest.py: Reuse existing fixtures rather than creating duplicates

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Coverage report reviewed and gaps identified
  - [ ] New test files created for uncovered code paths
  - [ ] `task test` passes with coverage ≥85% (ideally improved)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Test coverage improved
    Tool: Bash
    Preconditions: None
    Steps:
      1. Run: task test
      2. Compare coverage percentage to baseline
      3. Verify no existing tests were removed or broken
    Expected Result: Coverage ≥85%, no test regressions
    Failure Indicators: Coverage below 85% or any test failures
    Evidence: .sisyphus/evidence/task-3-coverage.md

  Scenario: Edge cases tested
    Tool: Bash
    Preconditions: New tests written
    Steps:
      1. Run: pytest tests/ -v -k "edge" or run full suite
      2. Verify edge case tests (empty body, huge headers, malformed request) pass
    Expected Result: All edge case tests pass
    Evidence: .sisyphus/evidence/task-3-edge-cases.md
  ```

  **Commit**: YES
  - Message: `test: add missing tests for acceleration, protocol, and server gaps`
  - Files: `tests/`
  - Pre-commit: `task test`

- [x] 4. Audit Rust Extension Status and Document Findings

  **What to do**:
  - Read `rust/palfrey_rust/src/lib.rs` — understand what functions are implemented
  - Read `palfrey_rust.pyi` — understand the Python interface/stubs
  - Read `palfrey/acceleration.py` — understand how Rust extension is detected and used
  - Try to build the Rust extension: `hatch run rust-build` (or `maturin develop` in rust/ directory)
  - Document findings: what works, what doesn't, what needs fixing
  - Check if Rust functions use `PyBackedBytes` (zero-copy) or `Vec<u8>` (copies data)
  - Check if `parse_request_head` returns bytes or strings (strings cause decode/encode overhead)
  - Record all findings in `.sisyphus/evidence/task-4-rust-audit.md`

  **Must NOT do**:
  - Do not make changes to Rust code in this task — audit only
  - Do not require Rust toolchain if not already installed

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires reading Rust code and understanding PyO3 bindings, maturin build system
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5, 6, 7)
  - **Blocks**: Task 14
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `rust/palfrey_rust/src/lib.rs` — The actual Rust implementation to audit
  - `palfrey/acceleration.py` — How Rust extension is imported and used; Python fallback code
  - `palfrey_rust.pyi` — Type stubs defining the Python-visible API

  **External References**:
  - PyO3 PyBackedBytes: Zero-copy pattern for passing bytes between Rust and Python
  - maturin docs: Build tool for PyO3 extensions

  **WHY Each Reference Matters**:
  - lib.rs: This IS the code to audit — need to understand return types, copy behavior, error handling
  - acceleration.py: Shows how Rust functions are called from Python — the integration point
  - pyi stubs: Defines expected function signatures that Rust must match

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Rust extension build attempt
    Tool: Bash
    Preconditions: Rust toolchain may or may not be installed
    Steps:
      1. Check if cargo/rustc are available: which cargo
      2. If available: attempt hatch run rust-build or maturin develop in rust/
      3. Record build success/failure and any error messages
      4. If built: import palfrey_rust in Python and verify functions exist
    Expected Result: Clear report of build status and function availability
    Failure Indicators: Build fails with unclear errors, or functions don't match stubs
    Evidence: .sisyphus/evidence/task-4-rust-audit.md

  Scenario: Audit Rust return types for performance
    Tool: Bash (read files)
    Preconditions: None (can read source without building)
    Steps:
      1. Read lib.rs — identify all #[pyfunction] exports
      2. Check return types: PyResult<String> (copies) vs PyResult<&PyBytes> (zero-copy)
      3. Check argument types: are inputs taken as &[u8] (zero-copy) or String (copy)?
      4. Document findings per function
    Expected Result: Per-function report of copy behavior
    Evidence: .sisyphus/evidence/task-4-rust-audit.md
  ```

  **Commit**: NO (audit only, no code changes)

- [x] 5. Module Docstrings — Core Modules (server, protocols, acceleration)

  **What to do**:
  - Add comprehensive module-level docstrings to the most critical modules:
    - `palfrey/server.py` — Explain PalfreyServer lifecycle, connection management, pipelining, concurrency slots, HTTP/2+3 handoff, keep-alive, graceful shutdown. Mention key classes: PalfreyServer, _ConnectionState.
    - `palfrey/protocols/http.py` — Explain HTTP/1.1 parsing pipeline, httptools vs h11 backends, ASGI scope building, request reading, response encoding, keep-alive decisions. Mention key functions: build_http_scope, run_http_asgi, encode_http_response, read_http_request.
    - `palfrey/protocols/http2.py` — Explain HTTP/2 integration via h2 library, stream multiplexing, flow control, server push if any. Mention key classes/functions.
    - `palfrey/protocols/http3.py` — Explain HTTP/3 via aioquic, QUIC transport, stream handling. Mention key classes/functions.
    - `palfrey/protocols/websocket.py` — Explain WebSocket lifecycle, backend selection (wsproto/websockets), upgrade flow, frame handling, backpressure.
    - `palfrey/acceleration.py` — Explain the acceleration shim pattern: try import Rust extension, fall back to pure Python. List all accelerated functions and their fallbacks.
  - Each docstring should be 5-15 lines, explaining: what the module does, key abstractions, how it fits into the server pipeline, notable design decisions
  - Follow Google-style docstrings (consistent with existing codebase patterns)

  **Must NOT do**:
  - Do not add boilerplate docstrings ("This module contains...") — each must explain WHY and HOW
  - Do not change any code behavior — docstring-only changes
  - Do not add docstrings that duplicate information already in function-level docstrings

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Primary concern is clear, accurate technical writing. Must read code deeply to write meaningful explanations.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4, 6, 7)
  - **Blocks**: Task 23 (API reference needs docstrings in place)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `palfrey/__init__.py` — Existing module docstring to follow as style guide
  - `palfrey/server.py:1-50` — Read the imports and class structure to understand module scope
  - `palfrey/protocols/http.py:1-80` — Read imports and top-level functions to understand module scope
  - `palfrey/acceleration.py:1-40` — Read the try/except import pattern to document

  **WHY Each Reference Matters**:
  - __init__.py: Shows existing docstring style (if any) to match
  - Each module's header: Must read to write accurate docstrings — don't describe what you haven't read

  **Acceptance Criteria**:

  - [ ] All 6 core modules have module-level docstrings
  - [ ] Each docstring is 5-15 lines, not boilerplate
  - [ ] `task lint` passes (docstrings don't break linting)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Module docstrings present and non-trivial
    Tool: Bash
    Preconditions: Docstrings written
    Steps:
      1. Run: python -c "import palfrey.server; print(palfrey.server.__doc__[:200])"
      2. Run: python -c "import palfrey.protocols.http; print(palfrey.protocols.http.__doc__[:200])"
      3. Run: python -c "import palfrey.acceleration; print(palfrey.acceleration.__doc__[:200])"
      4. Verify each prints non-empty, non-trivial content (not "This module...")
    Expected Result: All 3 imports succeed and print meaningful docstrings ≥50 chars
    Failure Indicators: ImportError, None output, or boilerplate text
    Evidence: .sisyphus/evidence/task-5-module-docstrings.md

  Scenario: Lint still passes
    Tool: Bash
    Preconditions: Docstrings written
    Steps:
      1. Run: task lint
    Expected Result: Clean pass
    Evidence: .sisyphus/evidence/task-5-lint.md
  ```

  **Commit**: YES (groups with Task 6)
  - Message: `docs: add module docstrings to core modules`
  - Files: `palfrey/server.py`, `palfrey/protocols/http.py`, `palfrey/protocols/http2.py`, `palfrey/protocols/http3.py`, `palfrey/protocols/websocket.py`, `palfrey/acceleration.py`
  - Pre-commit: `task lint`

- [x] 6. Module Docstrings — Supporting Modules (loops, middleware, adapters, config, etc.)

  **What to do**:
  - Add comprehensive module-level docstrings to all remaining modules without docstrings:
    - `palfrey/config.py` — Configuration parsing, CLI integration, env var model, default values
    - `palfrey/loops/auto.py` — Event loop auto-detection: uvloop if available, else asyncio
    - `palfrey/loops/uvloop.py` — uvloop integration, when/why to use it
    - `palfrey/loops/asyncio_loop.py` — Default asyncio loop setup
    - `palfrey/middleware/` — All middleware modules (list each and describe)
    - `palfrey/adapters/` — Adapter modules (Gunicorn worker, etc.)
    - `palfrey/types.py` — Type definitions shared across modules
    - Any other modules found without docstrings during the audit
  - Same quality requirements as Task 5: 5-15 lines, explain WHY and HOW, not boilerplate

  **Must NOT do**:
  - Do not add boilerplate docstrings
  - Do not change any code behavior

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical writing task requiring code comprehension
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4, 5, 7)
  - **Blocks**: Task 23 (API reference needs docstrings)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `palfrey/config.py:1-50` — Read to understand configuration module scope
  - `palfrey/loops/auto.py` — Small file, read entirely to document accurately
  - `palfrey/loops/uvloop.py` — Small file, read entirely
  - All files in `palfrey/middleware/` and `palfrey/adapters/` — Read to document

  **WHY Each Reference Matters**:
  - Must read each module before writing its docstring to ensure accuracy
  - Pattern from Task 5's core module docstrings provides consistency template

  **Acceptance Criteria**:

  - [ ] All supporting modules have module-level docstrings
  - [ ] Module docstring coverage reaches 100% (all .py files under palfrey/)
  - [ ] `task lint` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 100% module docstring coverage
    Tool: Bash
    Preconditions: All docstrings written
    Steps:
      1. Run: python -c "
         import ast, pathlib
         missing = []
         for p in pathlib.Path('palfrey').rglob('*.py'):
             tree = ast.parse(p.read_text())
             if not ast.get_docstring(tree):
                 missing.append(str(p))
         print(f'Missing: {len(missing)}')
         for m in missing: print(f'  {m}')
         assert len(missing) == 0, f'{len(missing)} modules still missing docstrings'
         "
    Expected Result: "Missing: 0" — all modules have docstrings
    Failure Indicators: Any module listed as missing
    Evidence: .sisyphus/evidence/task-6-docstring-coverage.md

  Scenario: Lint still passes
    Tool: Bash
    Steps:
      1. Run: task lint
    Expected Result: Clean pass
    Evidence: .sisyphus/evidence/task-6-lint.md
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `docs: add module docstrings to all supporting modules`
  - Files: `palfrey/config.py`, `palfrey/loops/*.py`, `palfrey/middleware/*.py`, `palfrey/adapters/*.py`, `palfrey/types.py`, any other modules
  - Pre-commit: `task lint`

- [x] 7. Profile HTTP Hot Paths with py-spy / cProfile

  **What to do**:
  - Profile the HTTP request/response hot path under realistic load using the existing benchmark harness:
    1. Start Palfrey serving the benchmark app: `python -m benchmarks.run --http-requests 10000` (or manually: `palfrey benchmarks.apps:http_app --port 8765`)
    2. Use py-spy to flame graph the running server during benchmark: `py-spy record -o .sisyphus/evidence/task-7-flamegraph.svg --pid <PID> --duration 30`
    3. Use cProfile for function-level timing: wrap the benchmark run with `python -m cProfile -o .sisyphus/evidence/task-7-cprofile.prof -m benchmarks.run --http-requests 50000`
    4. Analyze cProfile output: `python -c "import pstats; p = pstats.Stats('.sisyphus/evidence/task-7-cprofile.prof'); p.sort_stats('cumulative'); p.print_stats(30)"`
  - Identify the top 10 time-consuming functions in the HTTP hot path
  - Map them to specific optimization opportunities (Tasks 8-14)
  - Record findings in `.sisyphus/evidence/task-7-profile-report.md` with:
    - Top 10 functions by cumulative time
    - Top 10 functions by own time (excludes callees)
    - Flame graph observations (where are the thick bands?)
    - Specific optimization recommendations tied to Tasks 8-14

  **Must NOT do**:
  - Do not make performance changes in this task — profiling only
  - Do not install tools globally — use `pip install py-spy` in the project venv or `hatch run pip install py-spy`
  - Do not profile with unrealistically small payloads — use the existing benchmark app

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires setting up profiling tools, running benchmarks, interpreting flame graphs, and mapping findings to optimization targets
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-6)
  - **Blocks**: Tasks 8, 9, 10, 11, 12, 13, 14 (all Wave 2 performance tasks — profiling informs priorities)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — The benchmark harness: how it starts server, sends requests, measures
  - `benchmarks/apps.py` — The ASGI apps used in benchmarks: http_app, websocket_app

  **API/Type References**:
  - `palfrey/protocols/http.py:encode_http_response` — Expected to be top time consumer
  - `palfrey/protocols/http.py:build_http_scope` — Expected header processing overhead
  - `palfrey/protocols/http.py:read_http_request` — Expected body join overhead
  - `palfrey/server.py:_write_response` — Expected I/O overhead

  **External References**:
  - py-spy: `pip install py-spy` — sampling profiler for Python
  - cProfile: Built-in Python profiler for function-level timing

  **WHY Each Reference Matters**:
  - benchmarks/run.py: This IS the workload generator — understand how to run it and what it measures
  - HTTP functions: These are the suspected bottlenecks — profiling will confirm or refute

  **Acceptance Criteria**:

  - [ ] Flame graph SVG generated at `.sisyphus/evidence/task-7-flamegraph.svg`
  - [ ] cProfile output generated at `.sisyphus/evidence/task-7-cprofile.prof`
  - [ ] Profile report at `.sisyphus/evidence/task-7-profile-report.md` with top-10 functions

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Profiling produces actionable data
    Tool: Bash
    Preconditions: py-spy and cProfile available
    Steps:
      1. Install py-spy: pip install py-spy (or hatch run pip install py-spy)
      2. Run benchmark with cProfile: python -m cProfile -o /tmp/palfrey-prof.prof -m benchmarks.run --http-requests 20000
      3. Verify profile file exists and is non-empty: ls -la /tmp/palfrey-prof.prof
      4. Print top 10 cumulative: python -c "import pstats; p = pstats.Stats('/tmp/palfrey-prof.prof'); p.sort_stats('cumulative'); p.print_stats(10)"
    Expected Result: Profile shows function timings, top functions are identifiable HTTP path functions
    Failure Indicators: Empty profile, benchmark fails to run, or top functions are all asyncio internals with no Palfrey functions visible
    Evidence: .sisyphus/evidence/task-7-profile-output.md

  Scenario: Profile report maps findings to optimization tasks
    Tool: Bash
    Preconditions: Profile analysis complete
    Steps:
      1. Read .sisyphus/evidence/task-7-profile-report.md
      2. Verify it contains: top 10 functions list, optimization recommendations, references to Tasks 8-14
    Expected Result: Report exists with concrete function names and time percentages
    Evidence: .sisyphus/evidence/task-7-profile-report.md
  ```

  **Commit**: NO (evidence files only, no code changes)

- [x] 8. Streaming HTTP Response Writer (Eliminate Full-Body b"".join)

  **What to do**:
  - Replace `encode_http_response` in `protocols/http.py` which currently builds a single `bytes` object via `b"".join(parts)` (copying headers + entire body into one allocation) with a streaming writer that writes headers and body separately:
    1. Write TDD tests FIRST for the new streaming response path:
       - Test: small body (< 1KB) — single write is acceptable
       - Test: large body (> 64KB) — must NOT copy into single buffer
       - Test: empty body (204 No Content)
       - Test: chunked transfer encoding — frames written individually
       - Test: keep-alive header correctness preserved
    2. Modify `encode_http_response` to return an iterable/generator of byte chunks instead of single `bytes`, OR modify `_write_response` in `server.py` to use `writer.writelines()` with a list of [status_line, headers, CRLF, body] without joining
    3. Update `PalfreyServer._write_response` in `server.py` to use `writer.writelines()` or multiple `writer.write()` calls instead of single write
    4. Ensure the HTTP/1.1 chunked transfer encoding path also streams chunk frames individually
    5. Run benchmarks to verify improvement

  **Must NOT do**:
  - Do not break keep-alive behavior — connection reuse must still work
  - Do not change the ASGI interface (scope/receive/send contract)
  - Do not optimize HTTP/3 response path (correctness only per guardrails)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Performance-critical change to core HTTP write path. Requires understanding asyncio transport layer, buffering semantics, and ASGI send protocol.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9, 10, 11, 12, 13, 14)
  - **Blocks**: Task 15 (benchmark verification), Task 16 (HTTP/2 streaming)
  - **Blocked By**: Task 7 (profiling data informs priority)

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http.py` — `encode_http_response()` function: the current implementation that joins all parts. Find the `b"".join(parts)` line and the list construction above it.
  - `palfrey/server.py` — `_write_response()` method: where the encoded response bytes are written to `writer.write()`. This is the call site that needs updating.

  **API/Type References**:
  - `palfrey/protocols/http.py:HTTPResponse` — The response dataclass/namedtuple structure (status, headers, body)
  - `asyncio.StreamWriter.writelines()` — Accepts iterable of bytes, writes without joining

  **Test References**:
  - `tests/protocols/test_http_asgi.py` — Existing ASGI response tests to verify no regression
  - `tests/protocols/test_http_parser.py` — HTTP parsing tests

  **WHY Each Reference Matters**:
  - encode_http_response: This IS the function to modify — understand current parts list construction
  - _write_response: The call site — must update to use writelines or multiple writes
  - HTTPResponse: The data contract — must not change shape, only how it's serialized to wire

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests written FIRST for streaming response path
  - [ ] Tests cover: small body, large body, empty body, chunked encoding, keep-alive
  - [ ] `task test` passes with all new + existing tests

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Large body response does not copy into single buffer
    Tool: Bash
    Preconditions: Streaming writer implemented
    Steps:
      1. Create a test ASGI app that sends a 1MB body
      2. Run palfrey serving this app on port 18901
      3. curl http://127.0.0.1:18901 -o /dev/null -w "%{http_code} %{size_download}"
      4. Verify response is 200 with correct body size (1048576 bytes)
      5. Stop server
    Expected Result: HTTP 200, body size = 1048576, no OOM or excessive memory allocation
    Failure Indicators: HTTP error, truncated body, server crash
    Evidence: .sisyphus/evidence/task-8-streaming-large-body.md

  Scenario: Keep-alive still works with streaming writer
    Tool: Bash
    Preconditions: Streaming writer implemented
    Steps:
      1. Start palfrey with benchmark app on port 18902 in background
      2. Run the following Python script to verify keep-alive:
         python3 -c "
         import http.client, sys
         conn = http.client.HTTPConnection('127.0.0.1', 18902, timeout=5)
         results = []
         for i in range(3):
             conn.request('GET', '/')
             resp = conn.getresponse()
             body = resp.read()
             results.append((resp.status, len(body)))
             print(f'Request {i+1}: status={resp.status}, body_len={len(body)}')
         conn.close()
         # All 3 requests used the same connection (http.client reuses by default)
         assert all(s == 200 for s, _ in results), f'Not all 200: {results}'
         print('PASS: 3 requests succeeded on single keep-alive connection')
         sys.exit(0)
         "
      3. Capture script output
      4. Stop server
    Expected Result: All 3 requests return HTTP 200 on the same kept-alive connection, script prints "PASS" and exits 0
    Failure Indicators: ConnectionResetError, HTTP errors after first request, script exits non-zero
    Evidence: .sisyphus/evidence/task-8-keepalive.md

  Scenario: Existing tests still pass
    Tool: Bash
    Steps:
      1. Run: task test
    Expected Result: All tests pass, coverage ≥85%
    Evidence: .sisyphus/evidence/task-8-tests.md
  ```

  **Commit**: YES
  - Message: `perf: implement streaming HTTP response writer to eliminate full-body copy`
  - Files: `palfrey/protocols/http.py`, `palfrey/server.py`, `tests/protocols/test_http_response_streaming.py`
  - Pre-commit: `task lint && task test`

- [x] 9. Zero-Copy Header Handling — Keep Bytes in Hot Path

  **What to do**:
  - Eliminate the decode→re-encode cycle in the HTTP header hot path:
    1. Write TDD tests FIRST:
       - Test: headers arrive as bytes from httptools → stay as bytes through build_http_scope → appear as bytes in ASGI scope
       - Test: headers arrive from h11 → same treatment
       - Test: headers with non-ASCII values handled correctly
       - Test: header names are lowercased as bytes, not decoded to str then re-encoded
    2. In `protocols/http.py`, modify the httptools parser callbacks (`on_header`, `on_url`) to keep header data as bytes rather than decoding to `str`
    3. Modify `build_http_scope()` to construct the ASGI scope headers list directly from bytes, avoiding `name.lower().encode()` patterns
    4. Ensure the ASGI scope `headers` field contains `list[tuple[bytes, bytes]]` as per ASGI spec (it already should, but verify the path doesn't decode/re-encode)
    5. If Rust extension `parse_header_items` returns strings, note this for Task 14 but work around it in Python path

  **Must NOT do**:
  - Do not break ASGI spec compliance — headers must be bytes tuples in scope
  - Do not modify Rust extension code (that's Task 14)
  - Do not change public API of build_http_scope

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires deep understanding of httptools callback API, ASGI scope specification, and bytes vs str handling in Python
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 10, 11, 12, 13, 14)
  - **Blocks**: Task 15 (benchmark verification)
  - **Blocked By**: Task 7 (profiling data)

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http.py` — `_HTTPToolsParserProtocol.on_header(name, value)`: The httptools callback that receives parsed headers. Check if it decodes to str.
  - `palfrey/protocols/http.py` — `build_http_scope()`: Where headers are assembled into ASGI scope dict. Find encode() calls on header names/values.
  - `palfrey/protocols/http.py` — `_HTTPToolsParserProtocol.on_url(url)`: URL handling callback — check for unnecessary decode.

  **API/Type References**:
  - ASGI HTTP spec: `scope["headers"]` must be `Iterable[Tuple[bytes, bytes]]`
  - httptools callback signature: `on_header(name: bytes, value: bytes)` — httptools already provides bytes

  **WHY Each Reference Matters**:
  - on_header callback: This is where bytes enter the system — if they're decoded here, that's the root cause
  - build_http_scope: This is where scope is assembled — any encode() calls here are the symptom to eliminate
  - ASGI spec: The target format is bytes — so keeping bytes throughout avoids ALL conversion

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests verify headers stay as bytes through entire pipeline
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Headers remain bytes through pipeline (no decode/encode)
    Tool: Bash
    Preconditions: Zero-copy header handling implemented
    Steps:
      1. Create a test ASGI app that echoes received scope headers back in response body
      2. Start palfrey on port 18903
      3. curl -H "X-Custom: TestValue" -H "X-Binary: café" http://127.0.0.1:18903
      4. Verify response contains exact headers as bytes
      5. Stop server
    Expected Result: Headers preserved exactly, including non-ASCII bytes
    Failure Indicators: Header corruption, decode errors, missing headers
    Evidence: .sisyphus/evidence/task-9-header-bytes.md

  Scenario: No str.encode() in hot path (code inspection)
    Tool: Bash
    Steps:
      1. Search protocols/http.py for .encode() calls on header paths
      2. Verify no unnecessary str→bytes conversion in on_header, build_http_scope
    Expected Result: No encode() calls on header names/values in hot path
    Evidence: .sisyphus/evidence/task-9-code-inspection.md
  ```

  **Commit**: YES
  - Message: `perf: eliminate header decode/encode cycles in HTTP hot path`
  - Files: `palfrey/protocols/http.py`, `tests/protocols/test_http_header_bytes.py`
  - Pre-commit: `task lint && task test`

- [ ] 10. Eliminate Unconditional Body b"".join in read_http_request

  **What to do**:
  - The `read_http_request` function (and helpers `_read_chunked_body_chunks`, `_read_content_length_body_chunks`) currently collect all body chunks into a list and then `b"".join()` them, even for single-chunk bodies:
    1. Write TDD tests FIRST:
       - Test: single-chunk body (most common case) — returns the chunk directly, no join
       - Test: multi-chunk body — joins correctly
       - Test: empty body — returns b""
       - Test: chunked transfer encoding with multiple chunks
    2. Optimize the common case: if only one chunk was received, return it directly without `b"".join([chunk])` (which copies)
    3. For multi-chunk bodies, consider using `bytearray` + `.extend()` instead of list + `b"".join()` (less allocation)
    4. For the ASGI `receive` pathway: if the body is streamed to the app via multiple receive calls, ensure each chunk is passed through without buffering the whole body

  **Must NOT do**:
  - Do not break the ASGI receive contract
  - Do not change behavior for chunked transfer encoding correctness
  - Do not optimize at the expense of correctness for edge cases (e.g., Content-Length mismatch)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Focused optimization with clear scope — understand body reading paths and optimize allocation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 11, 12, 13, 14)
  - **Blocks**: Task 15
  - **Blocked By**: Task 7

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http.py` — `read_http_request()`: Main body reading function. Find the `b"".join(body_chunks)` call.
  - `palfrey/protocols/http.py` — `_read_chunked_body_chunks()`: Chunked transfer body reader
  - `palfrey/protocols/http.py` — `_read_content_length_body_chunks()`: Content-Length body reader

  **Test References**:
  - `tests/protocols/test_http_parser.py` — Existing body parsing tests
  - `tests/protocols/test_http_asgi.py` — ASGI body receive tests

  **WHY Each Reference Matters**:
  - read_http_request: The exact function to optimize — understand the chunk collection pattern
  - Chunk reader helpers: These produce the chunks that get joined — understand if they can yield directly

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests for single-chunk, multi-chunk, empty body, chunked encoding
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Single-chunk body avoids copy
    Tool: Bash
    Preconditions: Optimization implemented
    Steps:
      1. Create test ASGI app that receives body and echoes it
      2. Start palfrey on port 18904
      3. Send POST with small body: curl -X POST -d "hello" http://127.0.0.1:18904
      4. Verify response echoes "hello" correctly
      5. Send POST with large body (1MB): curl -X POST --data-binary @/dev/urandom http://127.0.0.1:18904 (or generate test data)
      6. Verify large body handled correctly
    Expected Result: Both small and large bodies handled correctly
    Failure Indicators: Truncated body, corruption, server error
    Evidence: .sisyphus/evidence/task-10-body-handling.md

  Scenario: Tests pass
    Tool: Bash
    Steps:
      1. Run: task test
    Expected Result: All pass, coverage ≥85%
    Evidence: .sisyphus/evidence/task-10-tests.md
  ```

  **Commit**: YES
  - Message: `perf: eliminate unconditional body join in request reading`
  - Files: `palfrey/protocols/http.py`, `tests/protocols/test_http_body_opt.py`
  - Pre-commit: `task lint && task test`

- [ ] 11. Socket Tuning — TCP_NODELAY, SO_REUSEPORT, Backlog

  **What to do**:
  - Audit and optimize socket-level settings for HTTP performance:
    1. Write TDD tests FIRST:
       - Test: TCP_NODELAY is set on accepted connections (reduces latency for small responses)
       - Test: SO_REUSEPORT is set on listener socket when multiple workers (Linux only)
       - Test: Backlog is configurable and defaults to a reasonable value (e.g., 2048)
       - Test: SO_REUSEADDR is set (standard for servers)
    2. In `server.py`, verify/add socket options on the server socket:
       - `SO_REUSEADDR` — standard, likely already set by asyncio
       - `SO_REUSEPORT` — optional, platform-dependent (Linux kernel ≥3.9), enables multi-worker load balancing
       - `TCP_NODELAY` — set on accepted connections via `transport.get_extra_info('socket')` or in protocol `connection_made`
       - Backlog — pass appropriate value to `loop.create_server(backlog=N)`
    3. Check if `TCP_QUICKACK` is available (Linux-only, reduces ACK delay)
    4. Make SO_REUSEPORT configurable via CLI/config (may already be)

  **Must NOT do**:
  - Do not use platform-specific options without checking availability (SO_REUSEPORT doesn't exist on macOS < 10.12, TCP_QUICKACK is Linux-only)
  - Do not change socket options that affect correctness (e.g., don't disable Nagle for WebSocket if it breaks framing)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systems-level socket programming, platform-specific conditionals, requires understanding asyncio transport layer
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 10, 12, 13, 14)
  - **Blocks**: Task 15
  - **Blocked By**: Task 7

  **References**:

  **Pattern References**:
  - `palfrey/server.py` — `PalfreyServer.serve()` or equivalent startup method: where `loop.create_server()` is called. Check existing socket options.
  - `palfrey/server.py` — Connection callback / `connection_made()`: where accepted connection transports are available for TCP_NODELAY.
  - `palfrey/config.py` — Configuration class: where backlog/socket options might be configurable.

  **External References**:
  - Python asyncio `loop.create_server()`: `backlog`, `reuse_address`, `reuse_port` parameters
  - `socket.TCP_NODELAY`, `socket.SO_REUSEPORT`, `socket.TCP_QUICKACK` constants

  **WHY Each Reference Matters**:
  - server.py startup: This is where socket options must be applied — at server creation time
  - connection_made: Per-connection options (TCP_NODELAY) must be set here on each accepted socket
  - config.py: Backlog should be configurable, not hardcoded

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests verify socket options are set correctly
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: TCP_NODELAY set on connections
    Tool: Bash
    Preconditions: Socket tuning implemented
    Steps:
      1. Start palfrey with benchmark app on port 18905
      2. Connect with: python -c "
         import socket
         s = socket.create_connection(('127.0.0.1', 18905))
         s.send(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
         print(s.recv(1024)[:100])
         s.close()
         "
      3. Verify connection succeeds and response is received
      4. Stop server
    Expected Result: Connection works, response received (TCP_NODELAY reduces latency but doesn't change behavior)
    Failure Indicators: Connection refused, timeout
    Evidence: .sisyphus/evidence/task-11-socket-tuning.md

  Scenario: Tests pass
    Tool: Bash
    Steps:
      1. Run: task test
    Expected Result: All pass
    Evidence: .sisyphus/evidence/task-11-tests.md
  ```

  **Commit**: YES
  - Message: `perf: add socket tuning (TCP_NODELAY, SO_REUSEPORT, configurable backlog)`
  - Files: `palfrey/server.py`, `palfrey/config.py`, `tests/server/test_socket_options.py`
  - Pre-commit: `task lint && task test`

- [ ] 12. Pre-Computed Status Lines + Cached Headers

  **What to do**:
  - Reduce per-response overhead by pre-computing common HTTP response components:
    1. Write TDD tests FIRST:
       - Test: status line for common codes (200, 201, 204, 301, 302, 400, 404, 500) are pre-computed bytes
       - Test: `Server` and `Date` headers are cached and refreshed appropriately
       - Test: uncommon status codes still work (fall through to dynamic generation)
    2. Create a module-level dict of pre-computed status lines:
       ```python
       _STATUS_LINES: dict[int, bytes] = {
           200: b"HTTP/1.1 200 OK\r\n",
           201: b"HTTP/1.1 201 Created\r\n",
           204: b"HTTP/1.1 204 No Content\r\n",
           301: b"HTTP/1.1 301 Moved Permanently\r\n",
           302: b"HTTP/1.1 302 Found\r\n",
           400: b"HTTP/1.1 400 Bad Request\r\n",
           404: b"HTTP/1.1 404 Not Found\r\n",
           500: b"HTTP/1.1 500 Internal Server Error\r\n",
           # ... all standard codes
       }
       ```
    3. Use lookup in `encode_http_response` instead of building status line dynamically each time
    4. Cache the `Server: palfrey` header as pre-encoded bytes
    5. Consider caching `Date` header with 1-second resolution (update via periodic callback)

  **Must NOT do**:
  - Do not cache Content-Type or Content-Length — these are per-response
  - Do not break custom status codes — fallback to dynamic generation
  - Do not add excessive memory usage for caching

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Well-defined optimization with clear scope — create dict, use lookup, add timer for date
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 10, 11, 13, 14)
  - **Blocks**: Task 15
  - **Blocked By**: Task 7

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http.py` — `encode_http_response()`: Where status line is currently built. Find the f-string or format call that creates `b"HTTP/1.1 200 OK\r\n"`.
  - `palfrey/server.py` — Where `Server:` header might be added to responses.

  **External References**:
  - HTTP/1.1 status codes: RFC 7231 Section 6 — complete list of reason phrases

  **WHY Each Reference Matters**:
  - encode_http_response: This is where status lines are built — need to understand current format to replace with lookup
  - Server header: Common per-response header that can be pre-computed once

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests for pre-computed status lines (common + uncommon fallback)
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Common status codes use pre-computed lines
    Tool: Bash
    Steps:
      1. python -c "
         from palfrey.protocols.http import _STATUS_LINES  # or whatever the dict is named
         assert b'200 OK' in _STATUS_LINES[200]
         assert b'404 Not Found' in _STATUS_LINES[404]
         print('Pre-computed status lines verified')
         "
    Expected Result: Assertion passes, status lines are pre-computed bytes
    Evidence: .sisyphus/evidence/task-12-status-lines.md

  Scenario: Uncommon status code still works
    Tool: Bash
    Steps:
      1. Create ASGI app that returns status 418 (I'm a Teapot)
      2. Start palfrey on port 18906
      3. curl -o /dev/null -w "%{http_code}" http://127.0.0.1:18906
      4. Verify response is 418
    Expected Result: HTTP 418 response (dynamic fallback works)
    Evidence: .sisyphus/evidence/task-12-uncommon-status.md
  ```

  **Commit**: YES
  - Message: `perf: add pre-computed status lines and cached server header`
  - Files: `palfrey/protocols/http.py`, `tests/protocols/test_http_status_cache.py`
  - Pre-commit: `task lint && task test`

- [x] 13. HTTP Write Backpressure (Port from WebSocket Path)

  **What to do**:
  - The WebSocket path in `protocols/websocket.py` has backpressure handling (checks `transport.get_write_buffer_size()` and pauses/resumes), but the HTTP write path does not:
    1. Write TDD tests FIRST:
       - Test: when write buffer exceeds high-water mark, writing pauses (drain)
       - Test: when buffer drops below low-water mark, writing resumes
       - Test: normal (non-congested) writes proceed without overhead
       - Test: chunked streaming responses respect backpressure
    2. Study the WebSocket backpressure pattern in `protocols/websocket.py` — find the `transport.get_write_buffer_size()` checks and `await writer.drain()` calls
    3. Port a similar pattern to the HTTP response write path in `server.py` (`_write_response`)
    4. Use `writer.drain()` after writes when buffer is above threshold
    5. Keep the backpressure check lightweight — don't add latency to normal (non-congested) writes

  **Must NOT do**:
  - Do not add backpressure overhead to every small response — only trigger when buffer fills
  - Do not change WebSocket backpressure behavior
  - Do not add configurable thresholds unless already patterned in the codebase

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding asyncio transport buffering, write drain semantics, and porting patterns between protocol handlers
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 10, 11, 12, 14)
  - **Blocks**: Task 15
  - **Blocked By**: Task 7

  **References**:

  **Pattern References**:
  - `palfrey/protocols/websocket.py` — Search for `drain` or `write_buffer_size` or `pause_writing` — this is the pattern to port
  - `palfrey/server.py` — `_write_response()` method: where HTTP responses are written to the transport. This is where backpressure check must be added.

  **API/Type References**:
  - `asyncio.StreamWriter.drain()` — Waits until write buffer is flushed below threshold
  - `asyncio.Transport.get_write_buffer_size()` — Current buffer fill level

  **WHY Each Reference Matters**:
  - WebSocket backpressure code: This is the PROVEN pattern already in the codebase — copy/adapt, don't reinvent
  - _write_response: This is where to ADD the check — understand the current write flow

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests for backpressure trigger, resume, and normal-path no-overhead
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Backpressure engages under load
    Tool: Bash
    Preconditions: Backpressure implemented
    Steps:
      1. Create ASGI app that sends large streaming response (10MB, chunked)
      2. Start palfrey on port 18907
      3. curl http://127.0.0.1:18907 -o /dev/null
      4. Verify: response completes without error, server doesn't OOM
    Expected Result: Full response received, server memory stays bounded
    Failure Indicators: OOM, truncated response, connection reset
    Evidence: .sisyphus/evidence/task-13-backpressure.md

  Scenario: Normal writes unaffected
    Tool: Bash
    Steps:
      1. Run: task test
      2. Run benchmark: hatch run benchmark (or python -m benchmarks.run --http-requests 50000)
      3. Verify performance hasn't regressed significantly (< 5% regression acceptable)
    Expected Result: Tests pass, benchmark within 5% of pre-backpressure baseline
    Evidence: .sisyphus/evidence/task-13-no-regression.md
  ```

  **Commit**: YES
  - Message: `perf: add HTTP write backpressure (ported from WebSocket path)`
  - Files: `palfrey/server.py`, `tests/server/test_http_backpressure.py`
  - Pre-commit: `task lint && task test`

- [x] 14. Rust Extension — Verify, Fix, Optimize

  **What to do**:
  - Based on Task 4's audit findings, take action on the Rust extension:
    1. Write TDD tests FIRST:
       - Test: `parse_request_head` returns correct result type (bytes preferred over str)
       - Test: `parse_header_items` correctly parses common header formats
       - Test: `split_csv_values` handles edge cases (empty, single, multiple)
       - Test: `unmask_websocket_payload` matches Python fallback output exactly
       - Test: All functions match Python fallback behavior exactly (fuzz-test with random inputs)
    2. If Rust extension builds:
       - Fix any build issues found in Task 4
       - Optimize return types: change `PyResult<String>` to `PyResult<Cow<[u8]>>` or `PyBackedBytes` where possible to avoid copies
       - Ensure `parse_request_head` returns bytes (not str) to eliminate decode/encode in hot path
       - Benchmark Rust path vs Python fallback
    3. If Rust extension does NOT build:
       - Fix maturin/PyO3 configuration to get it building
       - Update pyproject.toml build config if needed
       - Verify `import palfrey_rust` works after build
    4. Update `palfrey/acceleration.py` if function signatures changed
    5. Ensure pure Python fallback still works when Rust is not available (test with `PALFREY_NO_RUST=1` or by temporarily hiding the extension)

  **Must NOT do**:
  - Do not remove the pure Python fallback — it must always work
  - Do not require users to have Rust toolchain installed — Rust extension is optional
  - Do not change the acceleration.py public API (function signatures visible to other modules)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires Rust/PyO3 knowledge, maturin build system, cross-language optimization. Heaviest single task.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 10, 11, 12, 13)
  - **Blocks**: Task 15
  - **Blocked By**: Task 4 (audit findings needed)

  **References**:

  **Pattern References**:
  - `rust/palfrey_rust/src/lib.rs` — The Rust source code to fix/optimize
  - `palfrey_rust.pyi` — Type stubs that define expected function signatures
  - `palfrey/acceleration.py` — Import shim that tries Rust, falls back to Python
  - `.sisyphus/evidence/task-4-rust-audit.md` — Task 4's audit findings (will exist before this task runs)

  **Test References**:
  - `tests/unit/test_acceleration.py` — Existing tests for acceleration functions

  **External References**:
  - PyO3 docs: `PyBackedBytes`, `Cow<[u8]>` for zero-copy return types
  - maturin docs: Build configuration, develop mode

  **WHY Each Reference Matters**:
  - lib.rs: The code to modify — need to understand current function implementations
  - Task 4 audit: CRITICAL — tells us what works, what's broken, what to fix
  - acceleration.py: Integration point — if Rust signatures change, this must be updated

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests for all 4 Rust functions matching Python fallback behavior
  - [ ] `task test` passes with Rust extension loaded AND with fallback

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Rust extension builds and imports
    Tool: Bash
    Preconditions: Rust toolchain available (or verify it's not)
    Steps:
      1. Build: maturin develop (in rust/ directory) or hatch run rust-build
      2. Verify import: python -c "import palfrey_rust; print(dir(palfrey_rust))"
      3. Verify functions exist: python -c "from palfrey_rust import parse_request_head, parse_header_items, split_csv_values, unmask_websocket_payload; print('All functions available')"
    Expected Result: All 4 functions importable
    Failure Indicators: ImportError, missing functions
    Evidence: .sisyphus/evidence/task-14-rust-import.md

  Scenario: Rust functions match Python fallback exactly
    Tool: Bash
    Steps:
      1. python -c "
         from palfrey.acceleration import (
             parse_request_head as py_parse,
             parse_header_items as py_headers,
             split_csv_values as py_split,
         )
         # Test with sample inputs and compare outputs
         # (detailed comparison script)
         "
    Expected Result: Identical outputs for all test inputs
    Evidence: .sisyphus/evidence/task-14-rust-parity.md

  Scenario: Python fallback still works without Rust
    Tool: Bash
    Steps:
      1. PALFREY_NO_RUST=1 python -c "from palfrey.acceleration import parse_request_head; print('Fallback works')"
      2. PALFREY_NO_RUST=1 task test
    Expected Result: All tests pass using Python fallback
    Evidence: .sisyphus/evidence/task-14-fallback.md
  ```

  **Commit**: YES
  - Message: `perf: fix and optimize Rust extension with zero-copy returns`
  - Files: `rust/palfrey_rust/src/lib.rs`, `palfrey_rust.pyi`, `palfrey/acceleration.py`, `tests/unit/test_acceleration.py`
  - Pre-commit: `task lint && task test`

- [ ] 15. Benchmark Each Optimization Individually

  **What to do**:
  - After Wave 2 optimizations are complete, measure the individual impact of each change:
    1. Use the benchmark baseline captured in Task 1
    2. Run the full benchmark suite: `python -m benchmarks.run --http-requests 100000`
    3. Record aggregate improvement (total ops/s compared to baseline)
    4. If possible, isolate impact of each optimization:
       - Run benchmarks with git stash/cherry-pick of each optimization individually
       - OR use conditional flags to enable/disable optimizations
    5. Create a comprehensive performance report:
       - Baseline ops/s (from Task 1)
       - Current ops/s after all Wave 2 changes
       - Percentage improvement
       - Which optimizations contributed most
       - Comparison vs uvicorn (same benchmark conditions)
    6. Record in `.sisyphus/evidence/task-15-benchmark-report.md`

  **Must NOT do**:
  - Do not cherry-pick results — run same benchmark conditions as baseline
  - Do not modify benchmark harness (that's Task 17)
  - Do not claim improvements without evidence

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires careful methodology — running benchmarks, isolating variables, statistical interpretation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential — depends on ALL Wave 2 tasks)
  - **Blocks**: Task 30 (final comparison)
  - **Blocked By**: Tasks 8, 9, 10, 11, 12, 13, 14 (all Wave 2 performance tasks)

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — Benchmark harness, understand command-line options
  - `benchmarks/apps.py` — Test ASGI apps used in benchmarks
  - `.sisyphus/evidence/task-1-baseline.md` — Baseline numbers (from Task 1)

  **WHY Each Reference Matters**:
  - Baseline evidence: Must compare against same conditions
  - Benchmark harness: Must use same harness for fair comparison

  **Acceptance Criteria**:

  - [ ] Benchmark report at `.sisyphus/evidence/task-15-benchmark-report.md`
  - [ ] Report shows before/after comparison with percentage improvement
  - [ ] HTTP ops/s shows measurable improvement over baseline

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Benchmark runs and shows improvement
    Tool: Bash
    Preconditions: All Wave 2 optimizations applied
    Steps:
      1. Run: python -m benchmarks.run --http-requests 100000
      2. Record HTTP and WebSocket ops/s
      3. Compare to baseline in .sisyphus/evidence/task-1-baseline.md
      4. Calculate percentage change
    Expected Result: HTTP ops/s higher than baseline (measurable improvement)
    Failure Indicators: Regression (lower than baseline), benchmark fails to run
    Evidence: .sisyphus/evidence/task-15-benchmark-run.md

  Scenario: Performance report is comprehensive
    Tool: Bash
    Steps:
      1. Read .sisyphus/evidence/task-15-benchmark-report.md
      2. Verify sections: baseline, current, per-optimization, comparison
    Expected Result: Report contains all required sections with concrete numbers
    Evidence: .sisyphus/evidence/task-15-benchmark-report.md
  ```

  **Commit**: NO (evidence only)

- [ ] 16. HTTP/2 Streaming Response Optimization

  **What to do**:
  - Apply similar streaming optimizations from Task 8 to the HTTP/2 path:
    1. Write TDD tests FIRST:
       - Test: HTTP/2 large response doesn't buffer entire body before framing
       - Test: HTTP/2 stream flow control is respected
       - Test: HTTP/2 GOAWAY and RST_STREAM handling during streaming
    2. In `protocols/http2.py`, find where response body is joined before being split into DATA frames
    3. Optimize to stream body chunks directly as DATA frames without full-body buffering
    4. Respect h2 flow control windows — don't send more data than the window allows
    5. Ensure HTTP/2 header compression (HPACK) is working efficiently

  **Must NOT do**:
  - Do not break h2 library integration
  - Do not bypass h2 flow control (will break spec compliance)
  - Do not optimize at the expense of HTTP/2 correctness

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding h2 library API, HTTP/2 framing, flow control windows, and stream lifecycle
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 17, 18, 19, 20)
  - **Blocks**: Task 28
  - **Blocked By**: Task 8 (HTTP/1.1 streaming pattern to port)

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http2.py` — The HTTP/2 protocol handler. Find where response body is assembled and where DATA frames are sent.
  - `palfrey/protocols/http.py` — The HTTP/1.1 streaming writer (from Task 8) as a pattern to follow

  **Test References**:
  - `tests/protocols/test_http2*.py` — Existing HTTP/2 tests

  **External References**:
  - h2 library docs: `h2.connection.H2Connection.send_data()`, flow control API
  - HTTP/2 spec: DATA frame size limits, WINDOW_UPDATE semantics

  **WHY Each Reference Matters**:
  - http2.py: The code to modify — must understand h2 integration and current buffering
  - Task 8 pattern: Re-apply same streaming philosophy to HTTP/2

  **Acceptance Criteria**:

  **If TDD:**
  - [ ] Tests for HTTP/2 streaming responses, flow control, error handling
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: HTTP/2 large response streams correctly
    Tool: Bash
    Preconditions: HTTP/2 streaming optimization implemented
    Steps:
      1. Create ASGI app serving 1MB response
      2. Start palfrey with --http h2 on port 18908
      3. curl --http2 -k https://127.0.0.1:18908 -o /dev/null -w "%{http_code} %{size_download}"
      4. Verify: HTTP 200, full body received
    Expected Result: 200, size_download = 1048576
    Failure Indicators: Truncated response, protocol error, timeout
    Evidence: .sisyphus/evidence/task-16-http2-streaming.md

  Scenario: Tests pass
    Tool: Bash
    Steps:
      1. Run: task test
    Expected Result: All pass
    Evidence: .sisyphus/evidence/task-16-tests.md
  ```

  **Commit**: YES
  - Message: `perf: optimize HTTP/2 response streaming to avoid full-body buffering`
  - Files: `palfrey/protocols/http2.py`, `tests/protocols/test_http2_streaming.py`
  - Pre-commit: `task lint && task test`

- [ ] 17. Benchmark Methodology Upgrade — 3-Phase Approach

  **What to do**:
  - Upgrade the benchmark harness in `benchmarks/run.py` to use a rigorous 3-phase methodology:
    1. Write TDD tests FIRST:
       - Test: benchmark runner executes primer → warmup → measure phases
       - Test: primer phase completes without measuring
       - Test: warmup phase reaches stable throughput before measurement
       - Test: measurement phase reports mean, median, p99, stddev
    2. Implement 3-phase benchmarking:
       - **Primer** (5s): Small number of requests to warm up Python, JIT, caches. Results discarded.
       - **Warmup** (10s): Larger burst to reach steady state. Results discarded.
       - **Measure** (30s or N requests): Actual measurement period. Multiple runs, report statistics.
    3. Add statistical reporting:
       - Mean, median, p99, stddev for ops/s
       - Confidence interval (95%)
       - Outlier detection and flagging
    4. Add reproducibility features:
       - Print Python version, OS, CPU info, loop type
       - Save raw timing data to JSON for comparison
       - Support `--output` flag for machine-readable results

  **Must NOT do**:
  - Do not break the existing `python -m benchmarks.run` command — extend it
  - Do not remove the simple ops/s output — add statistical detail alongside
  - Do not make benchmarks take unreasonably long by default (keep under 2 minutes total)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Benchmark methodology requires statistical knowledge and careful implementation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 18, 19, 20)
  - **Blocks**: Task 30 (final benchmark)
  - **Blocked By**: Task 1 (baseline captured with current harness)

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — The current benchmark runner to extend
  - `benchmarks/apps.py` — ASGI apps used in benchmarks

  **External References**:
  - Python `statistics` module: mean, median, stdev
  - CodSpeed: `tests/benchmarks/` — existing microbenchmark patterns for reference

  **WHY Each Reference Matters**:
  - run.py: This IS the code to modify — understand current approach to extend, not replace
  - apps.py: The workloads — must remain compatible

  **Acceptance Criteria**:

  - [ ] 3-phase benchmarking implemented (primer, warmup, measure)
  - [ ] Statistical output: mean, median, p99, stddev
  - [ ] Backward compatible: `python -m benchmarks.run` still works
  - [ ] `task test` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 3-phase benchmark runs successfully
    Tool: Bash
    Steps:
      1. Run: python -m benchmarks.run --http-requests 10000
      2. Verify output shows: primer phase, warmup phase, measure phase
      3. Verify statistical output: mean, median, stddev present in output
    Expected Result: All 3 phases execute, statistical summary printed
    Failure Indicators: Missing phases, no statistical output, benchmark crash
    Evidence: .sisyphus/evidence/task-17-benchmark-3phase.md

  Scenario: Machine-readable output
    Tool: Bash
    Steps:
      1. Run: python -m benchmarks.run --http-requests 10000 --output /tmp/bench.json
      2. Verify JSON file: python -c "import json; d=json.load(open('/tmp/bench.json')); print(d.keys())"
    Expected Result: JSON contains structured benchmark results
    Evidence: .sisyphus/evidence/task-17-benchmark-json.md
  ```

  **Commit**: YES
  - Message: `feat: upgrade benchmark harness with 3-phase methodology and statistical reporting`
  - Files: `benchmarks/run.py`, `tests/benchmarks/test_benchmark_harness.py`
  - Pre-commit: `task lint && task test`

- [ ] 18. Function Docstrings — protocols/ Directory

  **What to do**:
  - Add or improve function/method docstrings in all `palfrey/protocols/` modules:
    - `http.py` — All public functions: `build_http_scope`, `run_http_asgi`, `encode_http_response`, `read_http_request`, `_read_chunked_body_chunks`, `_read_content_length_body_chunks`, `should_keep_alive`, parser callbacks
    - `http2.py` — All public functions/classes related to HTTP/2 stream handling
    - `http3.py` — All public functions/classes related to HTTP/3/QUIC handling
    - `websocket.py` — All public functions/classes for WebSocket lifecycle
  - Each docstring should follow Google style with:
    - One-line summary
    - Extended description for complex functions
    - Args section with types and descriptions
    - Returns section
    - Raises section (if applicable)
    - Example usage where helpful (for public API functions)
  - Focus on the 14% of functions currently missing docstrings, then improve existing thin ones

  **Must NOT do**:
  - Do not add boilerplate docstrings ("This function does X" restating the name)
  - Do not change any code behavior
  - Do not add docstrings to trivial one-liner helpers where the name is self-documenting

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical writing requiring deep code reading to produce accurate, useful docstrings
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 17, 19, 20)
  - **Blocks**: Task 23 (API reference generation depends on good docstrings)
  - **Blocked By**: Task 5 (module docstrings set style/conventions)

  **References**:

  **Pattern References**:
  - `palfrey/protocols/http.py` — All functions to document. Read each function to understand behavior before writing docstring.
  - `palfrey/protocols/websocket.py` — WebSocket functions to document.
  - Existing docstrings in the codebase — follow their style for consistency.

  **WHY Each Reference Matters**:
  - Must read each function to write accurate docstrings — do not guess or describe from names alone

  **Acceptance Criteria**:

  - [ ] All public functions in `palfrey/protocols/` have docstrings
  - [ ] Docstrings follow Google style with Args/Returns/Raises
  - [ ] `task lint` passes
  - [ ] Function docstring coverage in protocols/ ≥ 95%

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Protocol functions have docstrings
    Tool: Bash
    Steps:
      1. python -c "
         import ast, pathlib
         protocols_dir = pathlib.Path('palfrey/protocols')
         total = missing = 0
         for p in protocols_dir.glob('*.py'):
             tree = ast.parse(p.read_text())
             for node in ast.walk(tree):
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                     total += 1
                     if not ast.get_docstring(node):
                         missing += 1
                         print(f'  Missing: {p.name}:{node.name}:{node.lineno}')
         coverage = (total - missing) / total * 100 if total else 100
         print(f'Coverage: {coverage:.1f}% ({total - missing}/{total})')
         assert coverage >= 95, f'Coverage {coverage:.1f}% below 95%'
         "
    Expected Result: Function docstring coverage ≥ 95% in protocols/
    Evidence: .sisyphus/evidence/task-18-docstring-coverage.md

  Scenario: Lint passes
    Tool: Bash
    Steps:
      1. Run: task lint
    Expected Result: Clean pass
    Evidence: .sisyphus/evidence/task-18-lint.md
  ```

  **Commit**: YES (groups with Task 19)
  - Message: `docs: add function docstrings to protocol modules`
  - Files: `palfrey/protocols/http.py`, `palfrey/protocols/http2.py`, `palfrey/protocols/http3.py`, `palfrey/protocols/websocket.py`
  - Pre-commit: `task lint`

- [ ] 19. Function Docstrings — server.py, config.py, Remaining Modules

  **What to do**:
  - Add or improve function/method docstrings in all remaining modules:
    - `server.py` — Key methods: `PalfreyServer.__init__`, `serve`, `_handle_connection`, `_write_response`, `_handle_http`, `_handle_websocket`, shutdown methods
    - `config.py` — Configuration class methods, CLI integration functions
    - `acceleration.py` — All acceleration functions and their Python fallbacks
    - `loops/*.py` — Loop setup functions
    - `middleware/*.py` — Middleware functions/classes
    - `adapters/*.py` — Adapter classes (Gunicorn worker, etc.)
    - `_types.py` — Type alias explanations
  - Same quality requirements as Task 18: Google-style, Args/Returns/Raises, non-boilerplate

  **Must NOT do**:
  - Do not add boilerplate docstrings
  - Do not change any code behavior

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical writing requiring code comprehension
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 17, 18, 20)
  - **Blocks**: Task 23
  - **Blocked By**: Task 5 (module docstrings set convention)

  **References**:

  **Pattern References**:
  - `palfrey/server.py` — All public methods to document
  - `palfrey/config.py` — Configuration functions
  - `palfrey/acceleration.py` — Acceleration functions and fallbacks
  - Docstrings written in Task 18 — follow same style

  **WHY Each Reference Matters**:
  - Must read each function before documenting it

  **Acceptance Criteria**:

  - [ ] Overall function docstring coverage across entire `palfrey/` ≥ 95%
  - [ ] `task lint` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Project-wide function docstring coverage ≥ 95%
    Tool: Bash
    Steps:
      1. python -c "
         import ast, pathlib
         total = missing = 0
         for p in pathlib.Path('palfrey').rglob('*.py'):
             tree = ast.parse(p.read_text())
             for node in ast.walk(tree):
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                     total += 1
                     if not ast.get_docstring(node):
                         missing += 1
         coverage = (total - missing) / total * 100 if total else 100
         print(f'Overall coverage: {coverage:.1f}% ({total - missing}/{total})')
         assert coverage >= 95, f'Coverage {coverage:.1f}% below 95%'
         "
    Expected Result: Function docstring coverage ≥ 95%
    Evidence: .sisyphus/evidence/task-19-docstring-coverage.md

  Scenario: Lint passes
    Tool: Bash
    Steps:
      1. Run: task lint
    Expected Result: Clean pass
    Evidence: .sisyphus/evidence/task-19-lint.md
  ```

  **Commit**: YES (groups with Task 18)
  - Message: `docs: add function docstrings to server, config, and remaining modules`
  - Files: `palfrey/server.py`, `palfrey/config.py`, `palfrey/acceleration.py`, `palfrey/loops/*.py`, `palfrey/middleware/*.py`, `palfrey/adapters/*.py`
  - Pre-commit: `task lint`

- [ ] 20. Inline Code Comments for Complex Algorithms

  **What to do**:
  - Add inline comments to complex/non-obvious code sections across the codebase:
    - `server.py` — Pipelining queue logic, concurrency slot management, HTTP/2+3 protocol handoff detection, graceful shutdown sequence
    - `protocols/http.py` — httptools parser callback state machine, chunked encoding framing logic, keep-alive decision tree, ASGI scope construction
    - `protocols/websocket.py` — WebSocket upgrade flow, frame masking/unmasking, backpressure logic
    - `acceleration.py` — Why certain operations are accelerated, fallback strategy reasoning
  - Focus on the "WHY" not the "WHAT" — explain non-obvious decisions, not obvious code
  - Use concise comments (1-2 lines) inline, not block comments above every function

  **Must NOT do**:
  - Do not add comments to self-explanatory code (`i += 1  # increment i`)
  - Do not add excessive comments that create visual noise
  - Do not change any code behavior

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Code comprehension + clear technical explanation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 17, 18, 19)
  - **Blocks**: None
  - **Blocked By**: Tasks 8, 9, 10, 13 (comments should reflect the optimized code, not pre-optimization code)

  **References**:

  **Pattern References**:
  - `palfrey/server.py` — Complex sections needing comments (pipelining, concurrency, handoff)
  - `palfrey/protocols/http.py` — Parser state machine, encoding logic
  - `palfrey/protocols/websocket.py` — Backpressure logic

  **WHY Each Reference Matters**:
  - Must read and deeply understand each complex section to write accurate WHY comments

  **Acceptance Criteria**:

  - [ ] Complex algorithms have inline comments explaining WHY
  - [ ] No boilerplate/obvious comments added
  - [ ] `task lint` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Comments are present and non-trivial
    Tool: Bash
    Steps:
      1. Count inline comments in key files before/after: grep -c '#' palfrey/server.py palfrey/protocols/http.py
      2. Verify comment count increased
      3. Spot-check 3 comments are explaining WHY, not WHAT
    Expected Result: More comments, all explaining non-obvious decisions
    Evidence: .sisyphus/evidence/task-20-comments.md

  Scenario: Lint passes
    Tool: Bash
    Steps:
      1. Run: task lint
    Expected Result: Clean pass
    Evidence: .sisyphus/evidence/task-20-lint.md
  ```

  **Commit**: YES
  - Message: `docs: add inline comments for complex algorithms and non-obvious decisions`
  - Files: `palfrey/server.py`, `palfrey/protocols/http.py`, `palfrey/protocols/websocket.py`, `palfrey/acceleration.py`
  - Pre-commit: `task lint`

- [ ] 21. Uvicorn Migration Guide

  **What to do**:
  - Create a comprehensive migration guide for teams moving from Uvicorn to Palfrey:
    1. Create `docs/en/docs/guides/migrating-from-uvicorn.md`
    2. Cover:
       - **CLI mapping**: Every uvicorn CLI flag → Palfrey equivalent (table format)
       - **Configuration mapping**: Environment variables, config files
       - **Behavioral differences**: What's the same, what's different, what's new
       - **Gunicorn worker migration**: `uvicorn.workers.UvicornWorker` → `palfrey.workers.PalfreyWorker`
       - **Common gotchas**: Things that might surprise uvicorn users
       - **Step-by-step migration**: A concrete 5-step migration process
       - **Verification**: How to confirm your app works the same after migration
    3. Add code examples in `docs_src/migration/` using include directives (`{!> path !}`)
    4. Add the page to the nav in `docs/en/mkdocs.yml` under Guides section
    5. Also add to `mkdocs.yaml` nav under Guides

  **Must NOT do**:
  - Do not disparage uvicorn — Palfrey's README emphasizes respect for uvicorn
  - Do not claim superiority — present factual differences
  - Do not skip edge cases (WebSocket, HTTP/2, lifespan differences)

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation writing with deep understanding of both uvicorn and Palfrey CLIs and behavior
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 22, 23, 24, 25, 26, 27)
  - **Blocks**: Task 31 (docs build verification)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `docs/en/docs/guides/` — Existing guide pages for format/style reference
  - `docs/en/docs/reference/cli.md` — Palfrey's CLI reference (map from this)
  - `docs/en/docs/reference/configuration.md` — Palfrey's configuration options
  - `docs_src/` — How code examples are included with `{!> docs_src/path !}` syntax
  - `README.md` — The respectful comparison tone to follow

  **API/Type References**:
  - `palfrey/cli.py` — CLI definition, all flags and options
  - `palfrey/config.py` — Configuration parameters

  **External References**:
  - Uvicorn CLI docs: https://www.uvicorn.org/settings/ — for mapping flags

  **WHY Each Reference Matters**:
  - CLI reference: Source of truth for Palfrey flags — must be accurate mapping
  - README tone: Must match the respectful, non-competitive tone
  - docs_src pattern: Must follow the include directive pattern for code examples

  **Acceptance Criteria**:

  - [ ] `docs/en/docs/guides/migrating-from-uvicorn.md` exists with comprehensive content
  - [ ] Nav updated in both `docs/en/mkdocs.yml` and `mkdocs.yaml`
  - [ ] `task build` succeeds with new page
  - [ ] CLI mapping table is complete (all uvicorn flags mapped)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Migration guide builds in docs
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify: ls site/guides/migrating-from-uvicorn/index.html (or similar path)
    Expected Result: Page exists in built docs site
    Failure Indicators: Build fails, page missing from nav
    Evidence: .sisyphus/evidence/task-21-docs-build.md

  Scenario: CLI mapping is complete
    Tool: Bash
    Steps:
      1. Read the migration guide
      2. Verify it contains a table mapping uvicorn flags to palfrey equivalents
      3. Spot-check: --host, --port, --workers, --reload, --log-level all mapped
    Expected Result: All common uvicorn flags have Palfrey equivalents documented
    Evidence: .sisyphus/evidence/task-21-cli-mapping.md
  ```

  **Commit**: YES (groups with other docs tasks)
  - Message: `docs: add Uvicorn migration guide with CLI mapping and step-by-step process`
  - Files: `docs/en/docs/guides/migrating-from-uvicorn.md`, `docs/en/mkdocs.yml`, `mkdocs.yaml`, `docs_src/migration/`
  - Pre-commit: `task build`

- [ ] 22. Architecture Deep-Dive & Internals Documentation

  **What to do**:
  - Create documentation explaining Palfrey's internal architecture:
    1. Create `docs/en/docs/concepts/architecture.md`
    2. Cover:
       - **High-level architecture diagram** (Mermaid): Client → Transport → Protocol Parser → ASGI App → Response Writer
       - **Module map**: Which file handles what responsibility
       - **Connection lifecycle**: Accept → Parse → Route → Execute → Respond → Close/Keep-Alive
       - **Pipelining and concurrency**: How concurrent requests are managed, slot system
       - **Protocol selection**: How HTTP/1.1 vs HTTP/2 vs HTTP/3 is negotiated
       - **Acceleration layer**: How Rust/C extensions are detected and used, fallback strategy
       - **Event loop integration**: asyncio vs uvloop, when to use which
       - **Hot path analysis**: What code runs on every request (for performance-conscious users)
    3. Add Mermaid diagrams for visual clarity (mkdocs.yaml already has mermaid support)
    4. Add to nav in both mkdocs config files under Concepts

  **Must NOT do**:
  - Do not expose internal implementation details that might change — focus on stable concepts
  - Do not make it so detailed that it becomes stale quickly
  - Do not skip the Mermaid diagrams — visual architecture is critical for comprehension

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical documentation with deep architecture understanding. Must read code to describe accurately.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 23, 24, 25, 26, 27)
  - **Blocks**: Task 31
  - **Blocked By**: Tasks 8, 9 (architecture docs should reflect optimized code)

  **References**:

  **Pattern References**:
  - `palfrey/server.py` — Server class, connection lifecycle to describe
  - `palfrey/protocols/http.py` — HTTP pipeline to diagram
  - `palfrey/acceleration.py` — Acceleration layer to explain
  - `docs/en/docs/concepts/` — Existing concept pages for style reference

  **WHY Each Reference Matters**:
  - server.py: Core of the architecture — must read to describe connection lifecycle accurately
  - Existing concepts: Match writing style and depth for consistency

  **Acceptance Criteria**:

  - [ ] `docs/en/docs/concepts/architecture.md` exists with ≥ 3 Mermaid diagrams
  - [ ] Covers: module map, connection lifecycle, acceleration layer, protocol selection
  - [ ] Nav updated in both config files
  - [ ] `task build` succeeds

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Architecture page builds with Mermaid diagrams
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify architecture page exists in site output
      3. grep for "mermaid" in the built HTML to confirm diagrams render
    Expected Result: Page builds, Mermaid diagrams present
    Evidence: .sisyphus/evidence/task-22-docs-build.md

  Scenario: Content covers key architecture areas
    Tool: Bash
    Steps:
      1. Read docs/en/docs/concepts/architecture.md
      2. Verify sections: module map, connection lifecycle, acceleration, protocol selection
    Expected Result: All 4 key sections present with substantive content
    Evidence: .sisyphus/evidence/task-22-content-check.md
  ```

  **Commit**: YES (groups with other docs tasks)
  - Message: `docs: add architecture deep-dive with Mermaid diagrams`
  - Files: `docs/en/docs/concepts/architecture.md`, `docs/en/mkdocs.yml`, `mkdocs.yaml`
  - Pre-commit: `task build`

- [ ] 23. Auto-Generated API Reference (mkdocstrings)

  **What to do**:
  - Set up `mkdocstrings` to generate API reference documentation from docstrings:
    1. Create API reference pages in `docs/en/docs/reference/api/`:
       - `index.md` — Overview of API reference
       - `server.md` — `::: palfrey.server` with mkdocstrings directive
       - `http.md` — `::: palfrey.protocols.http`
       - `http2.md` — `::: palfrey.protocols.http2`
       - `http3.md` — `::: palfrey.protocols.http3`
       - `websocket.md` — `::: palfrey.protocols.websocket`
       - `config.md` — `::: palfrey.config`
       - `acceleration.md` — `::: palfrey.acceleration`
    2. Configure mkdocstrings in `mkdocs.yaml`:
       ```yaml
       plugins:
         - mkdocstrings:
             handlers:
               python:
                 options:
                   show_source: true
                   show_root_heading: true
                   docstring_style: google
       ```
    3. Add the API Reference section to nav in both config files
    4. Verify `task build` renders API docs correctly
    5. Note: mkdocstrings and mkdocstrings-python are already in `[project.optional-dependencies].docs`

  **Must NOT do**:
  - Do not expose private/internal functions (prefix with `_`) in API reference — use `show_if_no_docstring: false`
  - Do not add mkdocstrings config that conflicts with Zensical's build pipeline
  - Do not duplicate information already in concept pages

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires understanding mkdocstrings configuration, Zensical pipeline, and testing the build output
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22, 24, 25, 26, 27)
  - **Blocks**: Task 31
  - **Blocked By**: Tasks 5, 6, 18, 19 (docstrings must be in place for API reference to be useful)

  **References**:

  **Pattern References**:
  - `mkdocs.yaml` — Main config where mkdocstrings plugin must be added
  - `docs/en/mkdocs.yml` — Language-specific config that also needs plugin
  - `scripts/docs_pipeline.py` — Zensical build pipeline to understand how docs are assembled
  - `scripts/docs.py` — Build/serve commands to understand the full flow

  **External References**:
  - mkdocstrings docs: https://mkdocstrings.github.io/ — Configuration reference
  - mkdocstrings-python: https://mkdocstrings.github.io/python/ — Python handler options
  - griffe-typingdoc (already in deps): Typing-based documentation enhancement

  **WHY Each Reference Matters**:
  - mkdocs.yaml: Where plugin must be registered — wrong config will break build
  - docs pipeline: Must ensure mkdocstrings works with Zensical's prepare→build flow
  - griffe-typingdoc: Already a dependency — should be leveraged for better type display

  **Acceptance Criteria**:

  - [ ] API reference pages created for all major modules
  - [ ] mkdocstrings configured in mkdocs.yaml
  - [ ] `task build` succeeds and API pages render with function signatures and docstrings
  - [ ] Private functions excluded from API reference

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: API reference builds and shows function signatures
    Tool: Bash
    Steps:
      1. Run: task build
      2. Check built API reference page exists: ls site/reference/api/
      3. Verify server API page contains function signatures: grep "def " site/reference/api/server/index.html || grep "PalfreyServer" site/reference/api/server/index.html
    Expected Result: API pages built, contain function signatures from docstrings
    Failure Indicators: Build fails, API pages empty, mkdocstrings errors
    Evidence: .sisyphus/evidence/task-23-api-reference.md

  Scenario: Private functions excluded
    Tool: Bash
    Steps:
      1. Check API reference for private function names (prefixed with _)
      2. Verify they are NOT in the built output (or minimized)
    Expected Result: No private functions exposed in public API reference
    Evidence: .sisyphus/evidence/task-23-private-exclusion.md
  ```

  **Commit**: YES
  - Message: `docs: add auto-generated API reference using mkdocstrings`
  - Files: `docs/en/docs/reference/api/*.md`, `mkdocs.yaml`, `docs/en/mkdocs.yml`
  - Pre-commit: `task build`

- [ ] 24. Kubernetes / Helm Deployment Examples

  **What to do**:
  - Add practical Kubernetes deployment documentation:
    1. Create `docs/en/docs/operations/kubernetes.md`
    2. Create example files in `docs_src/kubernetes/`:
       - `deployment.yaml` — Basic Palfrey deployment
       - `service.yaml` — ClusterIP service
       - `hpa.yaml` — Horizontal Pod Autoscaler
       - `configmap.yaml` — Configuration via ConfigMap
       - `health-check.py` — Health check ASGI app example
    3. Cover:
       - **Deployment manifest**: Running Palfrey as container with correct args
       - **Resource requests/limits**: CPU and memory recommendations
       - **Health checks**: Liveness and readiness probes using Palfrey endpoints
       - **Scaling**: HPA configuration with request-rate metrics
       - **Configuration**: Environment variables via ConfigMap/Secret
       - **Graceful shutdown**: SIGTERM handling, preStop hooks, terminationGracePeriodSeconds
       - **Multi-worker**: When to use --workers vs multiple pods
    4. Include code examples using `{!> docs_src/kubernetes/deployment.yaml !}` syntax
    5. Add to nav under Operations in both config files

  **Must NOT do**:
  - Do not include Helm chart (too opinionated) — just raw manifests as examples
  - Do not include cloud-specific examples (GKE, EKS, AKS) — keep cloud-agnostic
  - Do not hardcode image names — use placeholders

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation with Kubernetes operational knowledge
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22, 23, 25, 26, 27)
  - **Blocks**: Task 31
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `docs/en/docs/operations/deployment.md` — Existing deployment docs for style
  - `docs/en/docs/operations/docker.md` — Docker docs (related)
  - `docs_src/` — Example snippet inclusion pattern
  - `palfrey/config.py` — Env var configuration to document for ConfigMap

  **WHY Each Reference Matters**:
  - Existing operations docs: Match style and depth
  - Config.py: Env vars that go into ConfigMap must be accurate

  **Acceptance Criteria**:

  - [ ] `docs/en/docs/operations/kubernetes.md` exists
  - [ ] Example YAML files in `docs_src/kubernetes/`
  - [ ] Nav updated in both config files
  - [ ] `task build` succeeds

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Kubernetes docs build
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify kubernetes page in site output
    Expected Result: Page builds successfully
    Evidence: .sisyphus/evidence/task-24-docs-build.md

  Scenario: YAML examples are valid
    Tool: Bash
    Steps:
      1. python -c "import yaml; yaml.safe_load(open('docs_src/kubernetes/deployment.yaml'))"
      2. python -c "import yaml; yaml.safe_load(open('docs_src/kubernetes/service.yaml'))"
    Expected Result: All YAML files parse without error
    Evidence: .sisyphus/evidence/task-24-yaml-valid.md
  ```

  **Commit**: YES (groups with other docs tasks)
  - Message: `docs: add Kubernetes deployment examples and operations guide`
  - Files: `docs/en/docs/operations/kubernetes.md`, `docs_src/kubernetes/*.yaml`, `docs/en/mkdocs.yml`, `mkdocs.yaml`
  - Pre-commit: `task build`

- [ ] 25. Reproducible Benchmark Playbook

  **What to do**:
  - Create a comprehensive benchmark playbook so users can reproduce Palfrey's benchmark results:
    1. Create `docs/en/docs/operations/benchmark-playbook.md`
    2. Cover:
       - **Prerequisites**: Python version, OS, hardware recommendations
       - **Environment setup**: Isolating from other processes, disabling turbo boost, CPU pinning
       - **Step-by-step benchmark process**:
         1. Install Palfrey with all optional deps
         2. Run the built-in benchmark: `python -m benchmarks.run --http-requests 100000`
         3. Run with uvicorn comparison
         4. Interpret results
       - **Benchmark variations**: HTTP/1.1, HTTP/2, WebSocket, different payload sizes
       - **Statistical validity**: How many runs, what's normal variance, when results are meaningful
       - **Common pitfalls**: Docker overhead, thermal throttling, background processes, noisy neighbors
       - **Reporting**: How to report benchmark results (template)
    3. Reference the upgraded benchmark harness from Task 17 (3-phase methodology)
    4. Add to nav under Operations in both config files

  **Must NOT do**:
  - Do not cherry-pick favorable benchmark conditions
  - Do not claim specific performance numbers that may not reproduce on different hardware
  - Do not skip the "common pitfalls" section

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical documentation requiring benchmark methodology expertise
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22, 23, 24, 26, 27)
  - **Blocks**: Task 31
  - **Blocked By**: Task 17 (benchmark methodology upgrade provides the process to document)

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — The benchmark harness to document
  - `benchmarks/apps.py` — Benchmark ASGI apps
  - `docs/en/docs/operations/benchmarks.md` — Existing benchmarks page (may overlap — reference or extend)
  - `README.md` — Benchmark snapshot format to reference

  **WHY Each Reference Matters**:
  - run.py: Must accurately document the CLI flags and process
  - Existing benchmarks page: Avoid duplication — either extend or link

  **Acceptance Criteria**:

  - [ ] `docs/en/docs/operations/benchmark-playbook.md` exists
  - [ ] Covers: prerequisites, step-by-step, statistical validity, pitfalls
  - [ ] `task build` succeeds

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Benchmark playbook builds
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify page exists in site output
    Expected Result: Page builds, contains step-by-step instructions
    Evidence: .sisyphus/evidence/task-25-docs-build.md
  ```

  **Commit**: YES (groups with other docs tasks)
  - Message: `docs: add reproducible benchmark playbook`
  - Files: `docs/en/docs/operations/benchmark-playbook.md`, `docs/en/mkdocs.yml`, `mkdocs.yaml`
  - Pre-commit: `task build`

- [ ] 26. Custom Protocol / Extension Tutorial

  **What to do**:
  - Create a tutorial for advanced users who want to extend Palfrey or build custom protocols:
    1. Create `docs/en/docs/guides/custom-protocols.md`
    2. Cover:
       - **How protocol handlers work**: The connection → parse → dispatch lifecycle
       - **Adding a custom middleware**: Step-by-step with code examples
       - **The acceleration layer**: How to add a new accelerated function with Rust + Python fallback
       - **Using Palfrey as a library**: Embedding Palfrey in a larger application
       - **Writing tests for custom extensions**: Patterns from Palfrey's test suite
    3. Add code examples in `docs_src/custom-protocols/`:
       - `middleware_example.py` — Simple custom middleware
       - `accel_example.py` — Custom acceleration function with fallback
    4. Add to nav under Guides in both config files

  **Must NOT do**:
  - Do not encourage monkey-patching or modifying Palfrey internals
  - Do not expose unstable internal APIs as extension points
  - Do not make the tutorial overly long — focus on the most common extension scenarios

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Tutorial writing requiring deep code understanding and pedagogical skill
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22, 23, 24, 25, 27)
  - **Blocks**: Task 31
  - **Blocked By**: Task 22 (architecture docs provide foundation for this tutorial)

  **References**:

  **Pattern References**:
  - `palfrey/middleware/` — Existing middleware implementations to explain patterns from
  - `palfrey/acceleration.py` — Acceleration layer to document as extension point
  - `docs/en/docs/guides/` — Existing guides for style reference

  **WHY Each Reference Matters**:
  - Middleware implementations: Source of truth for how middleware works in Palfrey
  - acceleration.py: The pattern to teach users for adding Rust-accelerated functions

  **Acceptance Criteria**:

  - [ ] `docs/en/docs/guides/custom-protocols.md` exists
  - [ ] Code examples in `docs_src/custom-protocols/`
  - [ ] `task build` succeeds

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Custom protocol tutorial builds
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify page exists in site output
    Expected Result: Page builds successfully
    Evidence: .sisyphus/evidence/task-26-docs-build.md

  Scenario: Code examples are valid Python
    Tool: Bash
    Steps:
      1. python -c "import ast; ast.parse(open('docs_src/custom-protocols/middleware_example.py').read())"
      2. python -c "import ast; ast.parse(open('docs_src/custom-protocols/accel_example.py').read())"
    Expected Result: Both Python files parse without syntax errors
    Evidence: .sisyphus/evidence/task-26-examples-valid.md
  ```

  **Commit**: YES (groups with other docs tasks)
  - Message: `docs: add custom protocol and extension tutorial`
  - Files: `docs/en/docs/guides/custom-protocols.md`, `docs_src/custom-protocols/*.py`, `docs/en/mkdocs.yml`, `mkdocs.yaml`
  - Pre-commit: `task build`

- [ ] 27. Expand Existing Documentation Pages with Examples

  **What to do**:
  - Audit and expand all existing documentation pages that lack sufficient examples:
    1. Review each page in the docs nav and identify pages that need more examples
    2. Priority pages to expand:
       - `concepts/http.md` — Add request/response lifecycle examples, header handling
       - `concepts/websockets.md` — Add connection upgrade, message handling examples
       - `concepts/lifespan.md` — Add startup/shutdown examples with real use cases (DB connections, caches)
       - `concepts/middleware.md` — Add custom middleware chain example
       - `reference/configuration.md` — Add example configs for common scenarios (development, production, CI)
       - `guides/from-zero-to-production.md` — Expand with more realistic production patterns
       - `operations/deployment.md` — Add systemd, supervisor examples
       - `reference/cli.md` — Add common command examples
    3. Create code examples in `docs_src/examples/` for each expansion
    4. Use `{!> docs_src/examples/path !}` include syntax for code blocks

  **Must NOT do**:
  - Do not rewrite existing content — only ADD examples and expand explanations
  - Do not add examples that duplicate code already in the docs
  - Do not add overly complex examples — keep them focused on one concept each

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation expansion requiring thorough page-by-page review
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22, 23, 24, 25, 26)
  - **Blocks**: Task 31
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - All files in `docs/en/docs/` — Review each for gaps
  - `docs_src/` — Existing code snippet pattern to follow
  - `docs/en/docs/getting-started/quickstart.md` — Good example of docs with code examples (benchmark for quality)

  **WHY Each Reference Matters**:
  - Must read existing pages to know what's missing before adding content
  - docs_src pattern: All code examples must follow the include directive pattern

  **Acceptance Criteria**:

  - [ ] At least 8 existing pages expanded with new examples
  - [ ] New code examples in `docs_src/examples/`
  - [ ] `task build` succeeds
  - [ ] No existing content removed or broken

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Expanded docs build successfully
    Tool: Bash
    Steps:
      1. Run: task build
      2. Verify no build warnings or errors
    Expected Result: Clean docs build
    Evidence: .sisyphus/evidence/task-27-docs-build.md

  Scenario: Code examples are valid
    Tool: Bash
    Steps:
      1. for f in docs_src/examples/*.py; do python -c "import ast; ast.parse(open('$f').read()); print(f'OK: $f')"; done
    Expected Result: All Python example files parse without errors
    Evidence: .sisyphus/evidence/task-27-examples-valid.md

  Scenario: No existing content removed
    Tool: Bash
    Steps:
      1. git diff --stat docs/en/docs/
      2. Verify all changes are additions (no deletions of existing content)
    Expected Result: Only additions, no deletions of existing content
    Evidence: .sisyphus/evidence/task-27-no-deletions.md
  ```

  **Commit**: YES
  - Message: `docs: expand existing documentation with additional examples and explanations`
  - Files: `docs/en/docs/concepts/*.md`, `docs/en/docs/reference/*.md`, `docs/en/docs/guides/*.md`, `docs/en/docs/operations/*.md`, `docs_src/examples/*.py`
  - Pre-commit: `task build`

- [ ] 28. Full Test Suite Pass + Coverage Verification

  **What to do**:
  - Run the complete test suite and fix any failures introduced by Wave 2-3 changes:
    1. Run: `task test` (full suite with coverage)
    2. If any tests fail:
       - Identify which task's changes caused the failure
       - Fix the failing tests or the implementation
       - Re-run until all pass
    3. Verify coverage ≥ 85%:
       - Run: `task coverage` for detailed coverage report
       - Identify any new code paths without coverage
       - Add targeted tests for uncovered paths
    4. Ensure no test is flaky — run suite 3 times consecutively
    5. Record final test results in `.sisyphus/evidence/task-28-test-results.md`

  **Must NOT do**:
  - Do not skip failing tests with `@pytest.mark.skip` — fix them
  - Do not lower coverage threshold
  - Do not add tests that are timing-dependent without proper async handling

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding test failures across the entire codebase, debugging, and systematic fixing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (sequential — must run after all implementation)
  - **Blocks**: F1, F2, F3, F4 (Final Verification)
  - **Blocked By**: Tasks 3, 8, 9, 10, 11, 12, 13, 14, 16 (all code-changing tasks)

  **References**:

  **Pattern References**:
  - `tests/` — Full test directory
  - `pyproject.toml:163-177` — Pytest configuration, markers, coverage settings
  - `Taskfile.yaml:101-116` — Test and coverage commands

  **WHY Each Reference Matters**:
  - Test configuration: Understand coverage thresholds and test markers
  - Taskfile: Know the exact commands to run

  **Acceptance Criteria**:

  - [ ] `task test` passes — 0 failures
  - [ ] Coverage ≥ 85%
  - [ ] Suite runs successfully 3 consecutive times (no flaky tests)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full test suite passes
    Tool: Bash
    Steps:
      1. Run: task test
      2. Verify: 0 failures, 0 errors
      3. Verify: coverage ≥ 85%
    Expected Result: All tests pass, coverage meets threshold
    Evidence: .sisyphus/evidence/task-28-test-results.md

  Scenario: Tests are not flaky
    Tool: Bash
    Steps:
      1. Run: task test (run 1)
      2. Run: task test (run 2)
      3. Run: task test (run 3)
      4. Verify all 3 runs have identical pass/fail results
    Expected Result: Consistent results across 3 runs
    Evidence: .sisyphus/evidence/task-28-stability.md
  ```

  **Commit**: YES (if fixes needed)
  - Message: `fix: resolve test failures and ensure full suite passes with ≥85% coverage`
  - Files: `tests/`, `palfrey/` (any files that needed fixes)
  - Pre-commit: `task test`

- [ ] 29. Final Lint / Type Check Clean Pass

  **What to do**:
  - Run all static analysis tools and fix any remaining issues:
    1. Run: `task lint` (ruff + ty)
    2. Fix ALL lint warnings and type errors:
       - ruff: Fix or document any remaining style issues
       - ty: Fix type annotation errors (NO `# type: ignore` without explanatory comment)
    3. Run: `hatch run format` to ensure consistent formatting
    4. Verify no new warnings introduced by any task's changes
    5. Record clean results in `.sisyphus/evidence/task-29-lint-clean.md`

  **Must NOT do**:
  - Do not add `# type: ignore` without a comment explaining why
  - Do not disable lint rules globally to pass
  - Do not suppress warnings — fix them

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic lint/type fixing across entire codebase
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 28, 30, 31 — but run after tests pass)
  - **Blocks**: F1, F2, F4
  - **Blocked By**: Task 28 (tests must pass first before final lint)

  **References**:

  **Pattern References**:
  - `pyproject.toml` — ruff and ty configuration sections
  - `.pre-commit-config.yaml` — Pre-commit hook configuration

  **WHY Each Reference Matters**:
  - Know what lint rules are configured and their severity levels

  **Acceptance Criteria**:

  - [ ] `task lint` passes cleanly (0 warnings, 0 errors)
  - [ ] Zero `# type: ignore` without explanatory comments
  - [ ] Code formatted with `hatch run format`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Clean lint pass
    Tool: Bash
    Steps:
      1. Run: task lint
      2. Verify exit code 0 and no warnings in output
    Expected Result: Clean pass — no warnings, no errors
    Evidence: .sisyphus/evidence/task-29-lint-clean.md

  Scenario: No bare type: ignore
    Tool: Bash
    Steps:
      1. Search for type: ignore without explanatory comment:
         grep -rn "type: ignore" palfrey/ --include="*.py" | grep -v "#.*type: ignore.*#"
      2. Verify: no results (all type: ignore have comments)
    Expected Result: Zero bare type: ignore directives
    Evidence: .sisyphus/evidence/task-29-type-ignore-check.md
  ```

  **Commit**: YES (if fixes needed)
  - Message: `fix: resolve remaining lint and type check issues for clean pass`
  - Files: `palfrey/` (any files fixed)
  - Pre-commit: `task lint`

- [ ] 30. Final Benchmark Comparison — Before vs After

  **What to do**:
  - Run the final comprehensive benchmark comparison:
    1. Use the upgraded benchmark harness from Task 17 (3-phase methodology)
    2. Run: `python -m benchmarks.run --http-requests 100000` (or equivalent with 3-phase)
    3. Create final comparison report:
       - **Baseline** (from Task 1): ops/s before any changes
       - **After optimization** (from Task 15): ops/s after Wave 2
       - **Final** (this task): ops/s with all changes including Wave 3+
       - **vs Uvicorn**: Run uvicorn with same benchmark and compare
    4. Calculate:
       - Total HTTP improvement percentage
       - Total WebSocket improvement (if any)
       - Relative speed vs uvicorn
    5. Save final report to `.sisyphus/evidence/task-30-final-benchmark.md`
    6. Update `README.md` benchmark snapshot if results are significantly better

  **Must NOT do**:
  - Do not cherry-pick results
  - Do not update README with unrepresentative numbers
  - Do not claim improvements without statistical evidence (stddev, multiple runs)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires careful benchmark methodology, statistical analysis, and report writing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 28, 29, 31)
  - **Blocks**: F1, F3
  - **Blocked By**: Tasks 15, 17 (benchmark infrastructure and prior results)

  **References**:

  **Pattern References**:
  - `benchmarks/run.py` — Benchmark harness (upgraded in Task 17)
  - `.sisyphus/evidence/task-1-baseline.md` — Original baseline
  - `.sisyphus/evidence/task-15-benchmark-report.md` — Post-optimization results
  - `README.md` — Benchmark snapshot table to potentially update

  **WHY Each Reference Matters**:
  - Baseline and prior results: For accurate before/after comparison
  - README: May need updating with new benchmark numbers

  **Acceptance Criteria**:

  - [ ] Final benchmark report at `.sisyphus/evidence/task-30-final-benchmark.md`
  - [ ] Report shows before/after/uvicorn comparison with statistics
  - [ ] HTTP performance shows measurable improvement over baseline
  - [ ] README updated if results warrant it

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Final benchmark shows improvement
    Tool: Bash
    Steps:
      1. Run: python -m benchmarks.run --http-requests 100000
      2. Compare HTTP ops/s to baseline (from Task 1)
      3. Run uvicorn benchmark for comparison
    Expected Result: Measurable HTTP improvement, comparison with uvicorn documented
    Evidence: .sisyphus/evidence/task-30-final-run.md

  Scenario: Comprehensive report generated
    Tool: Bash
    Steps:
      1. Read .sisyphus/evidence/task-30-final-benchmark.md
      2. Verify: baseline numbers, after-optimization, final numbers, uvicorn comparison, statistical measures
    Expected Result: Complete report with all comparison data
    Evidence: .sisyphus/evidence/task-30-final-benchmark.md
  ```

  **Commit**: YES (if README updated)
  - Message: `docs: update README benchmark snapshot with improved performance numbers`
  - Files: `README.md`
  - Pre-commit: `task lint`

- [ ] 31. Documentation Site Build Verification

  **What to do**:
  - Verify the entire documentation site builds cleanly with all new content:
    1. Run: `task build` (Zensical build pipeline)
    2. Verify:
       - Zero build warnings
       - Zero broken links
       - All new pages appear in navigation
       - All include directives (`{!> path !}`) resolve correctly
       - mkdocstrings API reference pages render function signatures
       - Mermaid diagrams in architecture page render (check for mermaid JS)
    3. Spot-check key pages in the built output:
       - Migration guide has CLI table
       - Architecture page has diagrams
       - API reference shows function signatures
       - Kubernetes examples show YAML
       - Benchmark playbook has step-by-step instructions
    4. Run link checker on built site if available
    5. Record verification in `.sisyphus/evidence/task-31-docs-build.md`

  **Must NOT do**:
  - Do not ignore build warnings — they indicate problems
  - Do not skip broken link checking

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires running doc build, inspecting output, validating multiple content types
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 28, 29, 30)
  - **Blocks**: F1, F3
  - **Blocked By**: Tasks 21, 22, 23, 24, 25, 26, 27 (all docs tasks)

  **References**:

  **Pattern References**:
  - `mkdocs.yaml` — Main config with nav and plugins
  - `docs/en/mkdocs.yml` — Language config
  - `scripts/docs.py` — Build command implementation
  - `scripts/docs_pipeline.py` — Include directive processing

  **WHY Each Reference Matters**:
  - Config files: Source of truth for what pages should appear
  - Pipeline scripts: Understanding how includes work to debug failures

  **Acceptance Criteria**:

  - [ ] `task build` exits 0 with no warnings
  - [ ] All new pages present in built site
  - [ ] No broken include directives
  - [ ] API reference pages render function signatures

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Documentation builds cleanly
    Tool: Bash
    Steps:
      1. Run: task build 2>&1 | tee /tmp/docs-build.log
      2. Verify exit code 0
      3. grep -i "warning\|error" /tmp/docs-build.log
      4. Verify: no warnings or errors
    Expected Result: Clean build, zero warnings
    Evidence: .sisyphus/evidence/task-31-build-log.md

  Scenario: All new pages present
    Tool: Bash
    Steps:
      1. Verify key pages exist:
         ls site/guides/migrating-from-uvicorn/
         ls site/concepts/architecture/
         ls site/reference/api/
         ls site/operations/kubernetes/
         ls site/operations/benchmark-playbook/
         ls site/guides/custom-protocols/
    Expected Result: All new pages present in site/ output
    Evidence: .sisyphus/evidence/task-31-pages-present.md

  Scenario: API reference renders function signatures
    Tool: Bash
    Steps:
      1. grep -l "PalfreyServer\|encode_http_response\|build_http_scope" site/reference/api/*/index.html
    Expected Result: Function names found in API reference HTML
    Evidence: .sisyphus/evidence/task-31-api-reference.md
  ```

  **Commit**: NO (verification only — fixes go into individual task re-runs)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `task lint` (ruff + ty). Run `task test`. Review all changed files for: `# type: ignore` without comment, empty catches, console.log/print in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Coverage [N%] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Run `task test` end-to-end. Run `hatch run benchmark` and verify improvement over baseline. Build docs with `task build`. Verify module docstring coverage via AST scan. Run the server and curl a test endpoint.
  Output: `Tests [PASS/FAIL] | Benchmark [before/after] | Docs Build [PASS/FAIL] | Docstrings [module%/func%] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

Commits should follow the project's conventions (from .claude/rules/commit-conventions.md):
- `fix: resolve type errors in server.py and websocket.py`
- `perf: implement streaming HTTP response writer`
- `perf: eliminate header decode/encode cycles in hot path`
- `perf: add socket tuning (TCP_NODELAY, SO_REUSEPORT)`
- `test: add TDD tests for streaming response writer`
- `docs: add module docstrings to all palfrey modules`
- `docs: add Uvicorn migration guide`
- `docs: add architecture deep-dive documentation`
- `refactor: eliminate unconditional body join in read_http_request`

Each performance task gets its own commit with benchmark evidence.
Each docs batch gets a commit. Tests committed alongside their implementation.

---

## Success Criteria

### Verification Commands
```bash
task lint          # Expected: clean pass (ruff + ty)
task test          # Expected: all pass, coverage ≥85%
task build         # Expected: docs site builds without errors
hatch run benchmark  # Expected: measurable HTTP improvement
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass with ≥85% coverage
- [ ] Zero LSP type errors in core modules
- [ ] Module docstrings: 100%
- [ ] Function docstrings: ≥95%
- [ ] Documentation site builds cleanly
- [ ] Benchmark shows measurable HTTP improvement
- [ ] No public API breaking changes
