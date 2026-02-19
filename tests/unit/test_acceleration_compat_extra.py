"""Additional acceleration fallback tests."""

from __future__ import annotations

import pytest

import palfrey.acceleration as acceleration


def test_split_csv_values_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.split_csv_values("127.0.0.1, 10.0.0.0/8 , ,unix:/tmp/socket") == [
        "127.0.0.1",
        "10.0.0.0/8",
        "unix:/tmp/socket",
    ]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (b"", "Missing request line"),
        (b"GET /only-two\r\n\r\n", "Invalid request line"),
        (b"GET / HTTP/1.1\r\nBadHeader\r\n\r\n", "Malformed header line"),
    ],
)
def test_parse_request_head_rejects_invalid_shapes(
    monkeypatch: pytest.MonkeyPatch,
    line: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    with pytest.raises(ValueError, match=message):
        acceleration.parse_request_head(line)


def test_parse_request_head_preserves_latin1_header_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    request_line = b"GET / HTTP/1.1\r\nX-Name: Caf\xe9\r\n\r\n"
    method, target, version, headers = acceleration.parse_request_head(request_line)
    assert (method, target, version) == ("GET", "/", "HTTP/1.1")
    assert headers == [("X-Name", "Caf\xe9")]


def test_parse_header_items_strips_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.parse_header_items(["x-a: one", "x-b:   two"]) == [
        ("x-a", "one"),
        ("x-b", "two"),
    ]
