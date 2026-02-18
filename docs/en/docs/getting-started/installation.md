# Installation

This page covers installation for local development, CI, and production-like environments.

## 1. Python Version

Palfrey targets modern Python.
Use a dedicated virtual environment per project.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 2. Install Palfrey

## Minimal install

```bash
pip install palfrey
```

## Install with common performance extras

```bash
pip install "palfrey[standard]"
```

## Local editable install for contributors

```bash
pip install -e ".[dev,testing,docs,benchmark,standard]"
```

## 3. Verify Installation

```bash
palfrey --version
```

You should see Palfrey version, Python implementation/version, and OS.

## 4. First App Verification

Create `main.py`:

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Run it:

```bash
palfrey main:app
```

Smoke test:

```bash
curl http://127.0.0.1:8000
```

## 5. Operator Notes (Non-Technical)

- Keep runtime dependencies pinned for repeatable deployments.
- Use the same install profile in CI and production build images when possible.
- Treat `--version` output as part of incident context capture.

## 6. Engineer Notes

- If `uvloop` is present and `--loop auto` is used, Palfrey can select it automatically.
- For structured logging configs (`.yaml`), install `PyYAML`.
- Keep base images lean and avoid adding dev extras to production images.

Continue to [Quickstart](quickstart.md).
