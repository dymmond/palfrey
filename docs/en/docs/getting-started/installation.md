# Installation

## Requirements

- Python 3.10+
- `pip`

## Base installation

```bash
pip install -e .
```

## Full development toolchain

```bash
scripts/install
```

This installs optional extras for:

- `standard` runtime extras (`httptools`, `uvloop`, `watchfiles`, `websockets`, etc.)
- `dev` tooling (`ruff`, `ty`, `maturin`)
- `testing` (`pytest`, `pytest-cov`)
- `docs` (`mkdocs-material` and docs plugins)

## Optional Rust extension build

```bash
scripts/build-rust-extension
```
