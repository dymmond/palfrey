from __future__ import annotations

import pytest

import palfrey.acceleration as acceleration


def test_parse_header_items_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.parse_header_items(["x-a: 1", "x-b: two"]) == [
        ("x-a", "1"),
        ("x-b", "two"),
    ]


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


def test_unmask_websocket_payload_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    payload = bytes([0x10, 0x20, 0x30, 0x40, 0x50])
    mask = bytes([0x01, 0x02, 0x03, 0x04])
    assert acceleration.unmask_websocket_payload(payload, mask) == bytes(
        [
            0x11,
            0x22,
            0x33,
            0x44,
            0x51,
        ]
    )


def test_unmask_websocket_payload_rejects_invalid_mask_length() -> None:
    with pytest.raises(ValueError, match="masking key must be exactly 4 bytes"):
        acceleration.unmask_websocket_payload(b"abc", b"\x01\x02\x03")
