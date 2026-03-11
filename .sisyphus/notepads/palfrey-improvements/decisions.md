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

## Documentation Recommendations for Palfrey Rust Extension

### Date: 2026-03-11
### Context: Research on pydantic, orjson, cryptography, polars

---

## Recommended Documentation Structure

### 1. Installation Page (Primary)

```markdown
# Installation

Install Palfrey from PyPI:

```bash
pip install palfrey
```

Pre-built wheels are available for:
- **Linux**: x86_64, aarch64 (manylinux)
- **macOS**: x86_64 (Intel), arm64 (Apple Silicon)
- **Windows**: x86_64

Most users can install directly without any build tools.

### Building from Source

If a pre-built wheel is not available for your platform:

1. Install Rust 1.83.0 or newer from https://rustup.rs
2. Install with: `pip install palfrey --no-binary palfrey`

**Note**: Rust is only required to **build** Palfrey, not to **use** it.
```

### 2. FAQ Section (Create New)

Add to documentation:

```markdown
## Frequently Asked Questions

### Do I need Rust installed to use Palfrey?

**No**. Rust is only required if you're building Palfrey from source.
Most users install pre-built wheels from PyPI which work out-of-the-box.

### Why does Palfrey use Rust?

Palfrey's performance-critical components are written in Rust to provide:
- **Speed**: [X]x faster than pure Python implementations
- **Memory safety**: Rust prevents entire classes of memory bugs
- **Reliability**: Compile-time guarantees for safer code

The Rust extension is transparent to users - the Python API remains unchanged.

### Installation failed with "Can not find Rust compiler"

**Solution 1**: Upgrade pip and try again:
```bash
pip install --upgrade pip
pip install palfrey
```

**Solution 2**: If your platform isn't supported by pre-built wheels:
- Install Rust from https://rustup.rs
- Build from source: `pip install palfrey --no-binary palfrey`

### What platforms are supported?

Pre-built wheels are available for:
- Linux (x86_64, aarch64) - manylinux2014+
- macOS 11+ (x86_64, arm64)
- Windows 10+ (x86_64)

For other platforms, you'll need to build from source.
```

### 3. Performance/Why Section (Update)

Add benefits-focused messaging:

```markdown
## Why Palfrey?

Palfrey provides [describe core value proposition] with:

- **Performance**: [X]x faster [operation] than [alternative]
- **Type Safety**: Rust-powered validation catches errors at compile time
- **Pythonic API**: Clean, familiar interface - no Rust knowledge required

### Benchmarks

[Include specific performance numbers comparing to alternatives]

### Under the Hood (Optional)

Palfrey uses a Rust extension for performance-critical operations while
maintaining a pure Python API. This gives you the best of both worlds:
native speed with Python's ease of use.
```

### 4. Contributing/Development Docs

```markdown
## Development Setup

### Prerequisites

- Python 3.8+
- Rust 1.83.0+ (install from https://rustup.rs)
- C compiler (gcc/clang on Linux, MSVC on Windows)

### Building from Source

```bash
git clone https://github.com/org/palfrey.git
cd palfrey
pip install -e .
```

The Rust extension will be compiled automatically during development install.
```

---

## User-Facing Messaging Guidelines

### DO Use These Phrases:

- "Pre-built wheels available for most platforms"
- "Rust is only required to BUILD, not to USE"
- "[X]x faster than [alternative]"
- "Works out-of-the-box with `pip install palfrey`"
- "No Rust knowledge required"

### DON'T Use These Phrases:

- "Requires Rust compiler" (in installation section)
- "PyO3 bindings to Rust core" (too technical)
- "Written in Rust" (focus on benefits, not implementation)
- "FFI layer for Python-Rust interop" (users don't need to know)

---

## Error Message Improvements

### Current Build Failure Messages

Review and update build error messages to match this pattern:

```
Error: Rust compiler not found

Palfrey requires Rust to build from source.

To fix this:
1. Upgrade pip: pip install --upgrade pip
2. Try installing again: pip install palfrey

If the error persists, install Rust from https://rustup.rs and try again.

For more help, see: https://palfrey.readthedocs.io/en/latest/faq.html
```

---

## Platform Support Communication

### Be Specific About Coverage

List exactly what platforms have pre-built wheels:

```markdown
## Platform Support

### Pre-built Wheels Available

| Platform | Architectures | Python Versions |
|----------|--------------|-----------------|
| Linux    | x86_64, aarch64 | 3.8, 3.9, 3.10, 3.11, 3.12 |
| macOS    | x86_64, arm64 | 3.8, 3.9, 3.10, 3.11, 3.12 |
| Windows  | x86_64 | 3.8, 3.9, 3.10, 3.11, 3.12 |

### Other Platforms

For platforms not listed above, you can build from source.
See [Building from Source](#building-from-source).
```

---

## Documentation Hierarchy

### Information Architecture

```
docs/
├── getting-started/
│   ├── installation.md     # Wheels first, build second
│   └── quickstart.md
├── user-guide/
│   └── ...
├── faq.md                  # Rust questions here
├── performance.md          # Benchmarks & benefits
└── contributing/
    └── development.md      # Build from source details
```

### Content Priority

**Page 1 (Installation)**:
- Simple `pip install` command
- Link to troubleshooting
- Link to FAQ

**Page 2 (FAQ)**:
- Do I need Rust? (No)
- Why Rust? (Performance & safety)
- Build failed? (Upgrade pip)

**Page 3 (Performance)**:
- Benchmarks with numbers
- When to use Palfrey vs alternatives

**Page 4 (Contributing)**:
- Full build-from-source instructions
- Rust installation details

---

## Action Items for Palfrey

1. **Add FAQ Section**
   - "Do I need Rust?" → No, only for building
   - "Why Rust?" → Performance + safety
   - "Build failed?" → Upgrade pip first

2. **Update Installation Docs**
   - Lead with simple `pip install palfrey`
   - Add platform support table
   - Move build instructions to secondary section

3. **Add Performance Page** (Optional but Recommended)
   - Benchmark numbers vs alternatives
   - Clear value proposition
   - Technical details in collapsible section

4. **Improve Error Messages**
   - User-friendly Rust compiler error
   - Link to FAQ/troubleshooting
   - Actionable next steps

5. **Document Platform Support**
   - List wheel availability explicitly
   - Set clear expectations
   - Explain build-from-source as fallback

---

## Key Principles (from research)

1. **99/1 Rule**: 99% of users get wheels, 1% build from source. Docs should reflect this.

2. **Benefits First**: Talk about speed/safety, not implementation.

3. **No Rust Knowledge Required**: Users shouldn't need to understand Rust to use the package.

4. **Clear Error Messages**: If build fails, provide actionable steps.

5. **Transparent but Not Noisy**: Mention Rust exists, explain why, don't make it users' problem.
