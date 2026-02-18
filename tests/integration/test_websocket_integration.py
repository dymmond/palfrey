"""WebSocket integration tests using Palfrey subprocess."""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
import subprocess
import sys
import time

import pytest


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            pytest.skip(f"Socket bind not permitted in this environment: {exc}")
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise TimeoutError("Timed out waiting for server startup")


def _send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(payload)
    mask = os.urandom(4)

    if length <= 125:
        header.append(0x80 | length)
    elif length <= 65_535:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))

    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _recv_text(sock: socket.socket) -> str:
    first_two = sock.recv(2)
    opcode = first_two[0] & 0x0F
    length = first_two[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    payload = sock.recv(length)
    if opcode != 0x1:
        raise RuntimeError("Unexpected websocket opcode")
    return payload.decode("utf-8")


def test_websocket_echo_roundtrip() -> None:
    port = _available_port()
    command = [
        sys.executable,
        "-m",
        "palfrey",
        "tests.fixtures.apps:websocket_app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--lifespan",
        "on",
    ]

    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        _wait_for_port(port)
        nonce = base64.b64encode(os.urandom(16)).decode("ascii")

        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            request = (
                "GET / HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {nonce}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            conn.sendall(request.encode("ascii"))
            handshake = conn.recv(4096)
            assert b"101 Switching Protocols" in handshake

            expected = base64.b64encode(
                hashlib.sha1(
                    (nonce + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
                    usedforsecurity=False,
                ).digest()
            )
            assert expected in handshake

            _send_text(conn, "hello")
            assert _recv_text(conn) == "hello"
    finally:
        process.terminate()
        process.wait(timeout=10)
