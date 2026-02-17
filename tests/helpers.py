"""Test helpers shared across Palfrey test modules."""

from __future__ import annotations

import asyncio


def make_stream_reader(payload: bytes) -> asyncio.StreamReader:
    """Create a stream reader preloaded with payload bytes."""

    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()
    return reader
