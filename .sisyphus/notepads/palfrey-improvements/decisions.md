# Architectural Decisions

This notepad tracks key architectural and design decisions made during implementation.

---

## Initial Context

- **Target Compatibility**: Linux, macOS, Windows (same as uvicorn)
- **Native Extensions**: Rust (PyO3) + httptools (C) + uvloop (Cython) — all optional with Python fallbacks
- **Protocol Support**: HTTP/1.1, HTTP/2, HTTP/3
- **Performance Target**: Profiling-driven, measurable improvement over baseline (not locked to specific multiplier)
- **TDD Workflow**: RED → GREEN → REFACTOR (tests first, always)

## Decisions Log

_(To be populated as decisions are made during implementation)_

---

_Updated by subagents when architectural choices are made._
