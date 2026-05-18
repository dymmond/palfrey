#!/bin/bash
# Wrapper to run benchmarks with venv python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use venv python to ensure dependencies are available
exec .venv/bin/python -m benchmarks.run "$@"
