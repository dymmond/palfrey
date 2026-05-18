"""Palfrey: A clean-room, high-performance Python ASGI server.

Palfrey is built with source-traceable parity mapping and focuses on:
- Behavior you can reason about
- Deployment controls you can operate safely
- Performance you can reproduce and verify

This module exports the public API including configuration, server, and runtime utilities.
"""

__version__ = "0.1.3"

from palfrey.config import Config, PalfreyConfig
from palfrey.main import main, run
from palfrey.server import PalfreyServer, Server

__all__ = [
    "main",
    "run",
    "Config",
    "Server",
    "PalfreyConfig",
    "PalfreyServer",
]
