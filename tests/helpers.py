"""Test helpers shared across Palfrey test modules."""

from __future__ import annotations

import asyncio


async def make_stream_reader(payload: bytes) -> asyncio.StreamReader:
    """Create a stream reader preloaded with payload bytes.

    The reader must be created within a running event loop for Python 3.13+.
    """

    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()
    return reader
