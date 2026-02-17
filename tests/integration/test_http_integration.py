"""HTTP integration tests using the real Palfrey CLI subprocess."""

from __future__ import annotations

import socket
import subprocess
import sys
import time


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
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


def test_http_roundtrip() -> None:
    port = _available_port()
    command = [
        sys.executable,
        "-m",
        "palfrey",
        "tests.fixtures.apps:http_app",
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

        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            conn.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            response = conn.recv(4096)

        assert b"200" in response
        assert b"ok" in response
    finally:
        process.terminate()
        process.wait(timeout=10)
