# Installation

This page covers local setup, CI setup, and production installation profiles.

## Prerequisites

- Python 3.10+
- `pip` available
- shell access to run `palfrey --version`

Optional but common:

- `uvloop` for high-performance loop mode on supported platforms
- `httptools` for HTTP parser backend
- `websockets` for websocket backend options
- `watchfiles` for reload mode

## Step 1: Create an Isolated Environment

## macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## Step 2: Choose an Install Profile

## Minimal runtime

```bash
pip install palfrey
```

Use this when you want the leanest dependency footprint.

## Standard runtime extras

```bash
pip install "palfrey[standard]"
```

Use this when you want common performance and feature extras.

## Contributor/developer setup

```bash
pip install -e ".[dev,testing,docs,benchmark,standard]"
```

Use this if you run tests, docs, lint, and benchmarks locally.

## Step 3: Verify Installation

```bash
palfrey --version
```

Expected output includes:

- Palfrey version
- Python implementation and version
- OS name

## Step 4: Smoke Test with a Minimal App

Create `main.py`:

```python
{!> ../../../docs_src/getting_started/hello_world.py !}
```

Run:

```bash
palfrey main:app --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000
```

## Troubleshooting Installation

## Command not found: `palfrey`

- confirm virtual environment is activated
- run `python -m pip show palfrey`
- if needed, run with module form: `python -m palfrey main:app`

## Optional backend package not installed

If you select an explicit backend (`--http httptools`, `--ws websockets`, etc.), ensure the package is installed.

## YAML log config fails to load

Install `PyYAML` (included in `standard` extras).

## For Non-Technical Readers

Installation profiles are simply bundles.

- minimal: least software installed
- standard: common extras included
- contributor: everything needed to build, test, and document

Next step: [Quickstart](quickstart.md)
