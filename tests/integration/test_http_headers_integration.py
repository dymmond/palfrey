"""Integration tests for default/custom HTTP response headers."""

from __future__ import annotations

import socket
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


def _request_headers(port: int) -> dict[str, str]:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        response = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            response += chunk

    header_bytes = response.split(b"\r\n\r\n", 1)[0]
    lines = header_bytes.split(b"\r\n")[1:]
    headers: dict[str, str] = {}
    for line in lines:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        headers[key.decode("latin-1").lower()] = value.strip().decode("latin-1")
    return headers


def _run_server(extra_args: list[str]) -> tuple[subprocess.Popen[bytes], int]:
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
        *extra_args,
    ]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_port(port)
    return process, port


def test_default_headers_present() -> None:
    process, port = _run_server([])
    try:
        headers = _request_headers(port)
        assert headers["server"] == "palfrey"
        assert "date" in headers
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_no_server_header_flag_removes_server_header() -> None:
    process, port = _run_server(["--no-server-header"])
    try:
        headers = _request_headers(port)
        assert "server" not in headers
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_no_date_header_flag_removes_date_header() -> None:
    process, port = _run_server(["--no-date-header"])
    try:
        headers = _request_headers(port)
        assert "date" not in headers
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_custom_header_and_server_override_are_applied() -> None:
    process, port = _run_server(["--header", "x-extra: one", "--header", "server: edge"])
    try:
        headers = _request_headers(port)
        assert headers["x-extra"] == "one"
        assert headers["server"] == "edge"
    finally:
        process.terminate()
        process.wait(timeout=10)
