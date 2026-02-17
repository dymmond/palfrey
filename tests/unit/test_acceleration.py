"""Acceleration helper tests."""

from __future__ import annotations

import pytest

import palfrey.acceleration as acceleration


def test_parse_header_items_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.parse_header_items(["x-a: 1", "x-b: two"]) == [("x-a", "1"), ("x-b", "two")]


def test_parse_header_items_rejects_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    with pytest.raises(acceleration.HeaderParseError):
        acceleration.parse_header_items(["missing-colon"])


def test_parse_request_head_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    request_head = b"GET /health HTTP/1.1\r\nhost: example.com\r\nx-test: yes\r\n\r\n"
    method, target, version, headers = acceleration.parse_request_head(request_head)
    assert method == "GET"
    assert target == "/health"
    assert version == "HTTP/1.1"
    assert headers == [("host", "example.com"), ("x-test", "yes")]
