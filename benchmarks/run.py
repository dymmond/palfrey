"""Run reproducible Palfrey vs Uvicorn benchmarks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "benchmarks.apps:app"


@dataclass(slots=True)
class ScenarioResult:
    """Benchmark result for one server/scenario pair."""

    server: str
    scenario: str
    operations: int
    duration_seconds: float

    @property
    def ops_per_second(self) -> float:
        """Compute operations per second."""

        if self.duration_seconds <= 0:
            return 0.0
        return self.operations / self.duration_seconds


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise TimeoutError(f"Server did not become ready on port {port}")


def _build_command(server: str, port: int) -> list[str]:
    python = os.environ.get("PYTHON", "python3")
    if server == "palfrey":
        return [python, "-m", "palfrey", APP, "--host", "127.0.0.1", "--port", str(port)]
    return [python, "-m", "uvicorn", APP, "--host", "127.0.0.1", "--port", str(port)]


def _spawn_server(server: str, port: int) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        _build_command(server, port),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    _wait_for_port(port)
    return process


def _stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _http_worker(port: int, requests: int) -> int:
    completed = 0
    for _ in range(requests):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            payload = b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
            conn.sendall(payload)
            response = conn.recv(4096)
            if b"200" not in response:
                raise RuntimeError("HTTP benchmark received non-200 response")
            completed += 1
    return completed


def _run_http(port: int, requests: int, concurrency: int) -> tuple[int, float]:
    completed_total = 0
    lock = threading.Lock()

    per_worker = requests // concurrency
    remainder = requests % concurrency

    def worker(work: int) -> None:
        nonlocal completed_total
        completed = _http_worker(port, work)
        with lock:
            completed_total += completed

    threads: list[threading.Thread] = []
    start = time.perf_counter()
    for index in range(concurrency):
        work = per_worker + (1 if index < remainder else 0)
        thread = threading.Thread(target=worker, args=(work,), daemon=True)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    duration = time.perf_counter() - start
    return completed_total, duration


def _ws_handshake(sock: socket.socket, port: int) -> None:
    nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET / HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {nonce}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = sock.recv(4096)
    if b"101 Switching Protocols" not in response:
        raise RuntimeError("WebSocket handshake failed")

    expected = base64.b64encode(
        hashlib.sha1(
            (nonce + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    if expected not in response:
        raise RuntimeError("WebSocket accept key mismatch")


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
    first_two = _read_exact(sock, 2)
    opcode = first_two[0] & 0x0F
    length = first_two[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    payload = _read_exact(sock, length)
    if opcode != 0x1:
        raise RuntimeError("Unexpected websocket opcode")
    return payload.decode("utf-8")


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("Socket closed before reading expected payload")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _ws_worker(port: int, messages: int) -> int:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        _ws_handshake(sock, port)
        completed = 0
        for index in range(messages):
            payload = f"{random.randint(1, 999999)}-{index}"
            _ws_send_text(sock, payload)
            echoed = _ws_recv_text(sock)
            if echoed != payload:
                raise RuntimeError("WebSocket echo mismatch")
            completed += 1
        return completed


def _run_ws(port: int, clients: int, messages_per_client: int) -> tuple[int, float]:
    completed_total = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal completed_total
        completed = _ws_worker(port, messages_per_client)
        with lock:
            completed_total += completed

    threads: list[threading.Thread] = []
    start = time.perf_counter()
    for _ in range(clients):
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    duration = time.perf_counter() - start
    return completed_total, duration


def _benchmark_server(
    server: str,
    *,
    http_requests: int,
    http_concurrency: int,
    ws_clients: int,
    ws_messages: int,
) -> list[ScenarioResult]:
    port = _available_port()
    process = _spawn_server(server, port)
    try:
        http_ops, http_duration = _run_http(port, http_requests, http_concurrency)
        ws_ops, ws_duration = _run_ws(port, ws_clients, ws_messages)
    finally:
        _stop_server(process)

    return [
        ScenarioResult(
            server=server,
            scenario="http",
            operations=http_ops,
            duration_seconds=http_duration,
        ),
        ScenarioResult(
            server=server,
            scenario="websocket",
            operations=ws_ops,
            duration_seconds=ws_duration,
        ),
    ]


def _relative_ratio(results: list[ScenarioResult], scenario: str) -> float | None:
    palfrey = next(
        (item for item in results if item.server == "palfrey" and item.scenario == scenario),
        None,
    )
    uvicorn = next(
        (item for item in results if item.server == "uvicorn" and item.scenario == scenario),
        None,
    )
    if palfrey is None or uvicorn is None or uvicorn.ops_per_second == 0:
        return None
    return palfrey.ops_per_second / uvicorn.ops_per_second


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-requests", type=int, default=2000)
    parser.add_argument("--http-concurrency", type=int, default=20)
    parser.add_argument("--ws-clients", type=int, default=20)
    parser.add_argument("--ws-messages", type=int, default=50)
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()

    results: list[ScenarioResult] = []
    for server in ("uvicorn", "palfrey"):
        try:
            results.extend(
                _benchmark_server(
                    server,
                    http_requests=args.http_requests,
                    http_concurrency=args.http_concurrency,
                    ws_clients=args.ws_clients,
                    ws_messages=args.ws_messages,
                )
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Benchmark for {server} failed: {exc}")

    print("| Scenario | Server | Operations | Duration (s) | Ops/s |")
    print("| --- | --- | ---: | ---: | ---: |")
    for result in sorted(results, key=lambda entry: (entry.scenario, entry.server)):
        print(
            f"| {result.scenario} | {result.server} | {result.operations} | "
            f"{result.duration_seconds:.4f} | {result.ops_per_second:.2f} |"
        )

    for scenario in ("http", "websocket"):
        ratio = _relative_ratio(results, scenario)
        if ratio is None:
            print(f"- {scenario}: n/a")
        else:
            print(f"- {scenario}: {ratio:.3f}x (Palfrey / Uvicorn)")

    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(
                [
                    {
                        "server": result.server,
                        "scenario": result.scenario,
                        "operations": result.operations,
                        "duration_seconds": result.duration_seconds,
                        "ops_per_second": result.ops_per_second,
                    }
                    for result in results
                ],
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
