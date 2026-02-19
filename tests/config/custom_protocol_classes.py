"""Custom protocol class fixtures for config load parity tests."""

from __future__ import annotations

import asyncio


class DummyHTTPProtocol(asyncio.Protocol):
    """Test HTTP protocol class."""


class DummyWSProtocol(asyncio.Protocol):
    """Test websocket protocol class."""
