from __future__ import annotations

import importlib
import random
from typing import Any

import palfrey.acceleration as acceleration

pytest = importlib.import_module("pytest")


def test_parse_header_items_python_fallback(monkeypatch: Any) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.parse_header_items(["x-a: 1", "x-b: two"]) == [
        ("x-a", "1"),
        ("x-b", "two"),
    ]


def test_parse_header_items_rejects_invalid(monkeypatch: Any) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    with pytest.raises(acceleration.HeaderParseError):
        acceleration.parse_header_items(["missing-colon"])


def test_parse_request_head_python_fallback(monkeypatch: Any) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    request_head = b"GET /health HTTP/1.1\r\nhost: example.com\r\nx-test: yes\r\n\r\n"
    method, target, version, headers = acceleration.parse_request_head(request_head)
    assert method == "GET"
    assert target == "/health"
    assert version == "HTTP/1.1"
    assert headers == [("host", "example.com"), ("x-test", "yes")]


def test_unmask_websocket_payload_python_fallback(monkeypatch: Any) -> None:
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


def test_split_csv_values_edge_cases(monkeypatch: Any) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.split_csv_values("") == []
    assert acceleration.split_csv_values("gzip") == ["gzip"]
    assert acceleration.split_csv_values("gzip,  deflate ,, br,") == ["gzip", "deflate", "br"]


def test_parse_header_items_common_formats(monkeypatch: Any) -> None:
    monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
    assert acceleration.parse_header_items(
        [
            "Host: example.com",
            "X-Forwarded-For: 127.0.0.1",
            "Authorization: Bearer abc.def",
        ]
    ) == [
        ("Host", "example.com"),
        ("X-Forwarded-For", "127.0.0.1"),
        ("Authorization", "Bearer abc.def"),
    ]


@pytest.mark.skipif(not acceleration.HAS_RUST_EXTENSION, reason="Rust extension not available")
def test_rust_parse_request_head_returns_bytes() -> None:
    import palfrey_rust

    method, target, version, headers = palfrey_rust.parse_request_head(
        b"GET /demo HTTP/1.1\r\nHost: example.com\r\n\r\n"
    )
    assert isinstance(method, bytes)
    assert isinstance(target, bytes)
    assert isinstance(version, bytes)
    assert headers and isinstance(headers[0][0], bytes) and isinstance(headers[0][1], bytes)


def test_unmask_websocket_payload_matches_python_fallback_randomized(
    monkeypatch: Any,
) -> None:
    rng = random.Random(7)
    original_has = acceleration.HAS_RUST_EXTENSION
    for _ in range(64):
        payload = bytes(rng.randrange(0, 256) for _ in range(rng.randrange(0, 256)))
        mask = bytes(rng.randrange(0, 256) for _ in range(4))

        monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
        expected = acceleration.unmask_websocket_payload(payload, mask)

        monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", original_has)
        actual = acceleration.unmask_websocket_payload(payload, mask)
        assert actual == expected


def test_all_acceleration_functions_match_python_fallback_randomized(
    monkeypatch: Any,
) -> None:
    if not acceleration.HAS_RUST_EXTENSION:
        pytest.skip("Rust extension not available")

    rng = random.Random(42)
    headers_pool = [
        "Host: example.com",
        "Accept: text/plain",
        "Connection: keep-alive",
        "X-Token: a:b:c",
        "X-Name: Caf\xe9",
    ]

    for _ in range(100):
        header_lines = rng.sample(headers_pool, k=rng.randrange(1, len(headers_pool) + 1))
        csv_input = ", ".join(rng.sample(["gzip", "br", "deflate", "zstd"], k=rng.randrange(1, 4)))
        method = rng.choice(["GET", "POST", "PUT", "DELETE"])
        target = rng.choice(["/", "/health", "/api/v1/items?id=1"])
        request_head = (
            f"{method} {target} HTTP/1.1\r\n" + "\r\n".join(header_lines) + "\r\n\r\n"
        ).encode("latin-1")
        payload = bytes(rng.randrange(0, 256) for _ in range(rng.randrange(0, 128)))
        mask = bytes(rng.randrange(0, 256) for _ in range(4))

        monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", False)
        expected_headers = acceleration.parse_header_items(header_lines)
        expected_csv = acceleration.split_csv_values(csv_input)
        expected_head = acceleration.parse_request_head(request_head)
        expected_unmasked = acceleration.unmask_websocket_payload(payload, mask)

        monkeypatch.setattr(acceleration, "HAS_RUST_EXTENSION", True)
        actual_headers = acceleration.parse_header_items(header_lines)
        actual_csv = acceleration.split_csv_values(csv_input)
        actual_head = acceleration.parse_request_head(request_head)
        actual_unmasked = acceleration.unmask_websocket_payload(payload, mask)

        assert actual_headers == expected_headers
        assert actual_csv == expected_csv
        assert actual_head == expected_head
        assert actual_unmasked == expected_unmasked
