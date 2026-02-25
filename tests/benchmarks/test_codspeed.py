"""CodSpeed performance benchmarks for Palfrey hot-path functions."""

from __future__ import annotations

import os

import pytest

from palfrey.acceleration import (
    parse_header_items,
    parse_request_head,
    split_csv_values,
    unmask_websocket_payload,
)
from palfrey.http_date import cached_http_date_header

# ---------------------------------------------------------------------------
# HTTP date header caching
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_bench_cached_http_date_header() -> None:
    """Measure throughput of the per-second cached HTTP date header."""
    for _ in range(1_000):
        cached_http_date_header()


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_SAMPLE_HEADERS = [
    "Content-Type: application/json",
    "Authorization: Bearer tok_abc123",
    "X-Request-Id: 7f3a9b2c-1d4e-5f6a-8b7c-9d0e1f2a3b4c",
    "Accept-Encoding: gzip, deflate, br",
    "Cache-Control: no-cache",
]


@pytest.mark.benchmark
def test_bench_parse_header_items() -> None:
    """Benchmark header item parsing with a realistic set of headers."""
    for _ in range(1_000):
        parse_header_items(_SAMPLE_HEADERS)


# ---------------------------------------------------------------------------
# CSV value splitting
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_bench_split_csv_values() -> None:
    """Benchmark splitting comma-separated header values."""
    value = "gzip, deflate, br, zstd, identity"
    for _ in range(1_000):
        split_csv_values(value)


# ---------------------------------------------------------------------------
# HTTP request head parsing
# ---------------------------------------------------------------------------

_SAMPLE_REQUEST = (
    b"GET /api/v1/users?page=2&limit=50 HTTP/1.1\r\n"
    b"Host: example.com\r\n"
    b"Accept: application/json\r\n"
    b"Authorization: Bearer tok_abc123\r\n"
    b"User-Agent: palfrey-bench/1.0\r\n"
    b"Accept-Encoding: gzip, deflate, br\r\n"
    b"Connection: keep-alive\r\n"
    b"\r\n"
)


@pytest.mark.benchmark
def test_bench_parse_request_head() -> None:
    """Benchmark full HTTP request head parsing."""
    for _ in range(1_000):
        parse_request_head(_SAMPLE_REQUEST)


# ---------------------------------------------------------------------------
# WebSocket payload unmasking
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_bench_unmask_websocket_small_payload() -> None:
    """Benchmark WebSocket unmasking for a small chat-like payload (64 bytes)."""
    payload = os.urandom(64)
    mask = b"\xaa\xbb\xcc\xdd"
    for _ in range(1_000):
        unmask_websocket_payload(payload, mask)


@pytest.mark.benchmark
def test_bench_unmask_websocket_medium_payload() -> None:
    """Benchmark WebSocket unmasking for a medium JSON payload (4 KB)."""
    payload = os.urandom(4096)
    mask = b"\x12\x34\x56\x78"
    for _ in range(1_000):
        unmask_websocket_payload(payload, mask)
