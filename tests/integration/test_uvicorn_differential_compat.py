from __future__ import annotations

import base64
import importlib.util
import os
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

LOCAL_UVICORN_REPO = Path(
    os.environ.get("PALFREY_UVICORN_REPO", "/Users/tarsil/Projects/github/dymmond/uvicorn")
)


def _uvicorn_pythonpath() -> str | None:
    if importlib.util.find_spec("uvicorn") is not None:
        return None
    if LOCAL_UVICORN_REPO.exists():
        return str(LOCAL_UVICORN_REPO)
    return None


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


def _read_exact(sock: socket.socket, total: int, *, initial: bytes = b"") -> tuple[bytes, bytes]:
    data = bytearray(initial)
    if len(data) > total:
        return bytes(data[:total]), bytes(data[total:])

    while len(data) < total:
        chunk = sock.recv(total - len(data))
        if not chunk:
            raise RuntimeError("Unexpected socket EOF")
        data.extend(chunk)
    return bytes(data), b""


@contextmanager
def _spawn_server(
    module_name: str,
    app_path: str,
    *,
    extra_args: list[str] | None = None,
    pythonpath: str | None = None,
) -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    port = _available_port()
    command = [
        sys.executable,
        "-m",
        module_name,
        app_path,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--lifespan",
        "on",
    ]
    if extra_args:
        command.extend(extra_args)

    env = os.environ.copy()
    if pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        _wait_for_port(port)
        yield process, port
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _raw_http_exchange(port: int, *, method: str = "GET") -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        request = f"{method} / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
        conn.sendall(request.encode("ascii"))
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def _http_exchange(port: int, *, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    raw = _raw_http_exchange(port, method=method)
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_line = lines[0].decode("latin-1")
    status = int(status_line.split(" ", 2)[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        headers[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    return status, headers, body


def _decode_http_body(headers: dict[str, str], body: bytes) -> bytes:
    transfer_encoding = headers.get("transfer-encoding", "").lower()
    if "chunked" not in transfer_encoding:
        return body

    index = 0
    decoded = bytearray()
    total = len(body)
    while index < total:
        line_end = body.find(b"\r\n", index)
        if line_end == -1:
            raise RuntimeError("Malformed chunked payload")
        size_line = body[index:line_end].split(b";", 1)[0]
        size = int(size_line, 16)
        index = line_end + 2
        if size == 0:
            break
        chunk_end = index + size
        if chunk_end > total:
            raise RuntimeError("Truncated chunk payload")
        decoded.extend(body[index:chunk_end])
        index = chunk_end + 2
    return bytes(decoded)


def _parse_http_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_line = lines[0].decode("latin-1")
    status = int(status_line.split(" ", 2)[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        headers[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    return status, headers, body


def _read_http_response(sock: socket.socket) -> tuple[int, dict[str, str], bytes]:
    header_buffer = bytearray()
    while b"\r\n\r\n" not in header_buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("Unexpected EOF before HTTP headers")
        header_buffer.extend(chunk)

    header_bytes, _, remainder = bytes(header_buffer).partition(b"\r\n\r\n")
    status, headers, _ = _parse_http_response(header_bytes + b"\r\n\r\n")

    transfer_encoding = headers.get("transfer-encoding", "").lower()
    if "chunked" in transfer_encoding:
        body = bytearray(remainder)
        while b"0\r\n\r\n" not in body:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body.extend(chunk)
        return status, headers, bytes(body)

    content_length_value = headers.get("content-length")
    if content_length_value is None:
        return status, headers, remainder

    try:
        content_length = int(content_length_value)
    except ValueError:
        return status, headers, remainder

    body = bytearray(remainder)
    while len(body) < content_length:
        chunk = sock.recv(content_length - len(body))
        if not chunk:
            break
        body.extend(chunk)

    return status, headers, bytes(body[:content_length])


def _ws_send_text(sock: socket.socket, text: str) -> None:
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


def _ws_recv_text(sock: socket.socket) -> str:
    first_two, remaining = _read_exact(sock, 2)
    opcode = first_two[0] & 0x0F
    length = first_two[1] & 0x7F
    if length == 126:
        packed, remaining = _read_exact(sock, 2, initial=remaining)
        length = struct.unpack("!H", packed)[0]
    elif length == 127:
        packed, remaining = _read_exact(sock, 8, initial=remaining)
        length = struct.unpack("!Q", packed)[0]
    payload, _ = _read_exact(sock, length, initial=remaining)
    if opcode != 0x1:
        raise RuntimeError(f"Unexpected websocket opcode: {opcode}")
    return payload.decode("utf-8")


def _ws_recv_close(sock: socket.socket, *, initial: bytes = b"") -> tuple[int, str]:
    first_two, remaining = _read_exact(sock, 2, initial=initial)
    opcode = first_two[0] & 0x0F
    masked = (first_two[1] & 0x80) != 0
    length = first_two[1] & 0x7F
    if length == 126:
        packed, remaining = _read_exact(sock, 2, initial=remaining)
        length = struct.unpack("!H", packed)[0]
    elif length == 127:
        packed, remaining = _read_exact(sock, 8, initial=remaining)
        length = struct.unpack("!Q", packed)[0]

    mask_key = b""
    if masked:
        mask_key, remaining = _read_exact(sock, 4, initial=remaining)

    payload, _ = _read_exact(sock, length, initial=remaining)
    if masked:
        payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))

    if opcode != 0x8:
        raise RuntimeError(f"Unexpected websocket opcode: {opcode}")
    if len(payload) < 2:
        return 1005, ""
    close_code = struct.unpack("!H", payload[:2])[0]
    close_reason = payload[2:].decode("utf-8", errors="replace")
    return close_code, close_reason


def _ws_handshake_and_echo(port: int, text: str) -> tuple[int, str]:
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
        status_line = handshake.split(b"\r\n", 1)[0].decode("latin-1")
        status = int(status_line.split(" ", 2)[1])
        _ws_send_text(conn, text)
        return status, _ws_recv_text(conn)


def _ws_handshake_response(
    port: int,
    *,
    subprotocol_header: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        request_lines = [
            "GET / HTTP/1.1",
            f"Host: 127.0.0.1:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {nonce}",
            "Sec-WebSocket-Version: 13",
        ]
        if subprotocol_header:
            request_lines.append(f"Sec-WebSocket-Protocol: {subprotocol_header}")
        request = "\r\n".join(request_lines) + "\r\n\r\n"
        conn.sendall(request.encode("ascii"))
        return _read_http_response(conn)


def _ws_handshake_and_read_close(port: int) -> tuple[int, int, str]:
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

        handshake = bytearray()
        while b"\r\n\r\n" not in handshake:
            chunk = conn.recv(4096)
            if not chunk:
                raise RuntimeError("Unexpected EOF during websocket handshake")
            handshake.extend(chunk)

        headers_part, _, remainder = bytes(handshake).partition(b"\r\n\r\n")
        status_line = headers_part.split(b"\r\n", 1)[0].decode("latin-1")
        status = int(status_line.split(" ", 2)[1])
        close_code, close_reason = _ws_recv_close(conn, initial=remainder)
        return status, close_code, close_reason


def _run_server_to_exit(
    module_name: str,
    app_path: str,
    *,
    extra_args: list[str] | None = None,
    pythonpath: str | None = None,
    timeout: float = 10.0,
) -> int:
    port = _available_port()
    command = [
        sys.executable,
        "-m",
        module_name,
        app_path,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--lifespan",
        "on",
    ]
    if extra_args:
        command.extend(extra_args)

    env = os.environ.copy()
    if pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.terminate()
        process.wait(timeout=5)
        raise AssertionError("Server did not exit within timeout window.") from exc


def _cli_supports_option(
    module_name: str,
    option: str,
    *,
    pythonpath: str | None = None,
) -> bool:
    env = os.environ.copy()
    if pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    completed = subprocess.run(
        [sys.executable, "-m", module_name, "--help"],
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )
    return option in completed.stdout


def test_http_response_matches_uvicorn_for_fixture_app() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:http_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, uvicorn_body = _http_exchange(uvicorn_port)

    with _spawn_server("palfrey", "tests.fixtures.apps:http_app") as (
        _palfrey_process,
        palfrey_port,
    ):
        palfrey_status, palfrey_headers, palfrey_body = _http_exchange(palfrey_port)

    assert palfrey_status == uvicorn_status == 200
    assert (
        _decode_http_body(palfrey_headers, palfrey_body)
        == _decode_http_body(uvicorn_headers, uvicorn_body)
        == b"ok"
    )
    assert palfrey_headers.get("transfer-encoding") == uvicorn_headers.get("transfer-encoding")
    assert palfrey_headers.get("content-length") == uvicorn_headers.get("content-length")
    assert palfrey_headers.get("content-type") == uvicorn_headers.get("content-type")


def test_http_content_length_framing_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:http_content_length_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, uvicorn_body = _http_exchange(uvicorn_port)

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:http_content_length_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, palfrey_body = _http_exchange(palfrey_port)

    assert palfrey_status == uvicorn_status == 200
    assert (
        _decode_http_body(palfrey_headers, palfrey_body)
        == _decode_http_body(uvicorn_headers, uvicorn_body)
        == b"ok"
    )
    assert palfrey_headers.get("content-length") == uvicorn_headers.get("content-length")
    assert palfrey_headers.get("transfer-encoding") == uvicorn_headers.get("transfer-encoding")


def test_http_head_response_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:http_head_behavior_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, uvicorn_body = _http_exchange(
            uvicorn_port,
            method="HEAD",
        )

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:http_head_behavior_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, palfrey_body = _http_exchange(
            palfrey_port,
            method="HEAD",
        )

    assert palfrey_status == uvicorn_status == 200
    assert palfrey_body == uvicorn_body
    assert palfrey_headers.get("content-length") == uvicorn_headers.get("content-length")
    assert palfrey_headers.get("transfer-encoding") == uvicorn_headers.get("transfer-encoding")


def test_http_duplicate_set_cookie_headers_match_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:http_multi_set_cookie_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_raw = _raw_http_exchange(uvicorn_port)

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:http_multi_set_cookie_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_raw = _raw_http_exchange(palfrey_port)

    uvicorn_head = uvicorn_raw.partition(b"\r\n\r\n")[0].split(b"\r\n")[1:]
    palfrey_head = palfrey_raw.partition(b"\r\n\r\n")[0].split(b"\r\n")[1:]
    uvicorn_set_cookies = [line for line in uvicorn_head if line.lower().startswith(b"set-cookie:")]
    palfrey_set_cookies = [line for line in palfrey_head if line.lower().startswith(b"set-cookie:")]
    assert palfrey_set_cookies == uvicorn_set_cookies


def test_websocket_echo_matches_uvicorn_for_fixture_app() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_echo = _ws_handshake_and_echo(uvicorn_port, "hello")

    with _spawn_server("palfrey", "tests.fixtures.apps:websocket_app") as (
        _palfrey_process,
        palfrey_port,
    ):
        palfrey_status, palfrey_echo = _ws_handshake_and_echo(palfrey_port, "hello")

    assert palfrey_status == uvicorn_status == 101
    assert palfrey_echo == uvicorn_echo == "hello"


def test_websocket_close_frame_matches_uvicorn_for_fixture_app() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_close_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_close_code, uvicorn_close_reason = _ws_handshake_and_read_close(
            uvicorn_port
        )

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:websocket_close_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_close_code, palfrey_close_reason = _ws_handshake_and_read_close(
            palfrey_port
        )

    assert palfrey_status == uvicorn_status == 101
    assert palfrey_close_code == uvicorn_close_code == 1001
    assert palfrey_close_reason == uvicorn_close_reason == "custom reason"


def test_websocket_http_response_extension_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_http_response_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, uvicorn_body = _ws_handshake_response(uvicorn_port)

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:websocket_http_response_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, palfrey_body = _ws_handshake_response(palfrey_port)

    assert palfrey_status == uvicorn_status == 418
    assert (
        _decode_http_body(palfrey_headers, palfrey_body)
        == _decode_http_body(uvicorn_headers, uvicorn_body)
        == b"teapot"
    )
    assert palfrey_headers.get("content-type") == uvicorn_headers.get("content-type")
    assert palfrey_headers.get("transfer-encoding") == uvicorn_headers.get("transfer-encoding")
    assert palfrey_headers.get("content-length") == uvicorn_headers.get("content-length")


def test_websocket_subprotocol_accept_header_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_subprotocol_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, _ = _ws_handshake_response(
            uvicorn_port,
            subprotocol_header="chat, superchat",
        )

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:websocket_subprotocol_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, _ = _ws_handshake_response(
            palfrey_port,
            subprotocol_header="chat, superchat",
        )

    assert palfrey_status == uvicorn_status == 101
    assert (
        palfrey_headers.get("sec-websocket-protocol")
        == uvicorn_headers.get("sec-websocket-protocol")
        == "chat"
    )


def test_websocket_per_message_deflate_header_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_subprotocol_app",
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, _ = _ws_handshake_response(uvicorn_port)

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:websocket_subprotocol_app",
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, _ = _ws_handshake_response(palfrey_port)

    assert palfrey_status == uvicorn_status == 101
    uvicorn_extensions = uvicorn_headers.get("sec-websocket-extensions")
    palfrey_extensions = palfrey_headers.get("sec-websocket-extensions")
    assert bool(palfrey_extensions) == bool(uvicorn_extensions)
    if uvicorn_extensions:
        assert "permessage-deflate" in uvicorn_extensions.lower()
        assert palfrey_extensions is not None
        assert "permessage-deflate" in palfrey_extensions.lower()


def test_websocket_per_message_deflate_disable_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")
    if not _cli_supports_option(
        "uvicorn",
        "--no-ws-per-message-deflate",
        pythonpath=uvicorn_pythonpath,
    ):
        pytest.skip("uvicorn CLI does not support --no-ws-per-message-deflate in this environment")
    if not _cli_supports_option("palfrey", "--no-ws-per-message-deflate"):
        pytest.skip("palfrey CLI does not support --no-ws-per-message-deflate in this environment")

    with _spawn_server(
        "uvicorn",
        "tests.fixtures.apps:websocket_subprotocol_app",
        extra_args=["--no-ws-per-message-deflate"],
        pythonpath=uvicorn_pythonpath,
    ) as (_uvicorn_process, uvicorn_port):
        uvicorn_status, uvicorn_headers, _ = _ws_handshake_response(uvicorn_port)

    with _spawn_server(
        "palfrey",
        "tests.fixtures.apps:websocket_subprotocol_app",
        extra_args=["--no-ws-per-message-deflate"],
    ) as (_palfrey_process, palfrey_port):
        palfrey_status, palfrey_headers, _ = _ws_handshake_response(palfrey_port)

    assert palfrey_status == uvicorn_status == 101
    assert palfrey_headers.get("sec-websocket-extensions") == uvicorn_headers.get(
        "sec-websocket-extensions"
    )


def test_lifespan_startup_failure_exit_code_matches_uvicorn() -> None:
    uvicorn_pythonpath = _uvicorn_pythonpath()
    if uvicorn_pythonpath is None and importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed and local uvicorn repo is unavailable")

    uvicorn_code = _run_server_to_exit(
        "uvicorn",
        "tests.fixtures.apps:lifespan_fail_app",
        pythonpath=uvicorn_pythonpath,
    )
    palfrey_code = _run_server_to_exit(
        "palfrey",
        "tests.fixtures.apps:lifespan_fail_app",
    )

    assert palfrey_code == uvicorn_code
