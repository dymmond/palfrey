from __future__ import annotations

from palfrey.protocols.websocket import build_handshake_response


def test_websocket_handshake_response_contains_accept_key() -> None:
    headers = [
        ("host", "127.0.0.1"),
        ("upgrade", "websocket"),
        ("connection", "Upgrade"),
        ("sec-websocket-key", "dGhlIHNhbXBsZSBub25jZQ=="),
        ("sec-websocket-version", "13"),
    ]

    response = build_handshake_response(headers, subprotocol=None)
    assert b"101 Switching Protocols" in response
    assert b"sec-websocket-accept" in response
