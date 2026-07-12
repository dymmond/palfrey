"""Run reproducible Palfrey vs Uvicorn benchmarks."""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import math
import os
import platform
import random
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP = "benchmarks.apps:app"
RETRYABLE_CONNECT_ERRNOS = {
    errno.EADDRNOTAVAIL,
    errno.EADDRINUSE,
    errno.EAGAIN,
}


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


def _result_to_dict(result: ScenarioResult) -> dict[str, Any]:
    return {
        "server": result.server,
        "scenario": result.scenario,
        "operations": result.operations,
        "duration_seconds": result.duration_seconds,
        "ops_per_second": result.ops_per_second,
    }


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


def _create_connection_with_retry(
    host: str,
    port: int,
    *,
    timeout: float = 5.0,
    attempts: int = 200,
    initial_backoff: float = 0.005,
    max_backoff: float = 0.5,
) -> socket.socket:
    """Create a TCP connection with retry for transient local socket exhaustion."""

    backoff = initial_backoff
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            return socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            last_error = exc
            if exc.errno not in RETRYABLE_CONNECT_ERRNOS or attempt == attempts - 1:
                raise
            time.sleep(backoff * (1.0 + random.random() * 0.1))
            backoff = min(max_backoff, backoff * 2)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to create connection and no socket error was captured")


def _build_command(server: str, port: int) -> list[str]:
    python = os.environ.get("PYTHON", sys.executable)
    if server == "palfrey":
        return [
            python,
            "-m",
            "palfrey",
            APP,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--no-proxy-headers",
            "--http",
            "httptools",
            "--loop",
            "uvloop",
            "--ws",
            "websockets",
            "--ws-ping-interval",
            "0",
        ]
    return [
        python,
        "-m",
        "uvicorn",
        APP,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-access-log",
        "--no-proxy-headers",
        "--http",
        "httptools",
        "--loop",
        "uvloop",
        "--ws",
        "websockets",
    ]


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
    if requests <= 0:
        return 0

    keep_alive_payload = b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: keep-alive\r\n\r\n"
    close_payload = b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"

    conn: socket.socket | None = None
    completed = 0
    try:
        while completed < requests:
            is_last = completed == requests - 1
            if conn is None:
                conn = _create_connection_with_retry("127.0.0.1", port, timeout=5)

            payload = close_payload if is_last else keep_alive_payload
            try:
                conn.sendall(payload)
                status_code = _read_http_status_code(conn)
            except (OSError, RuntimeError):
                conn.close()
                conn = None
                continue

            if status_code != 200:
                raise RuntimeError("HTTP benchmark received non-200 response")
            completed += 1
            if is_last:
                conn.close()
                conn = None
    finally:
        if conn is not None:
            conn.close()

    return completed


def _read_http_status_code(sock: socket.socket) -> int:
    """Read one HTTP response and return status code."""

    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("Socket closed before HTTP headers were received")
        buffer.extend(chunk)

    head, _, remainder = bytes(buffer).partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if not lines:
        raise RuntimeError("Empty HTTP response head")
    status_line = lines[0].decode("latin-1")
    parts = status_line.split(" ", 2)
    if len(parts) < 2:
        raise RuntimeError(f"Malformed HTTP status line: {status_line!r}")

    try:
        status_code = int(parts[1])
    except ValueError as exc:
        raise RuntimeError(f"Malformed HTTP status code: {status_line!r}") from exc

    headers: dict[bytes, bytes] = {}
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        headers[name.strip().lower()] = value.strip()

    transfer_encoding = headers.get(b"transfer-encoding", b"").lower()
    if b"chunked" in transfer_encoding:
        _consume_chunked_body(sock, remainder)
        return status_code

    content_length = headers.get(b"content-length")
    if content_length is None:
        return status_code

    try:
        expected = int(content_length.decode("ascii"))
    except ValueError as exc:
        raise RuntimeError("Malformed Content-Length header in benchmark response") from exc

    body = bytearray(remainder)
    while len(body) < expected:
        chunk = sock.recv(expected - len(body))
        if not chunk:
            raise RuntimeError("Socket closed before full HTTP body was received")
        body.extend(chunk)

    return status_code


def _consume_chunked_body(sock: socket.socket, initial: bytes) -> None:
    """Consume one chunked HTTP body from socket stream."""

    body = bytearray(initial)
    index = 0

    def ensure(size: int) -> None:
        while len(body) < size:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Socket closed before full chunked body was received")
            body.extend(chunk)

    while True:
        while True:
            line_end = body.find(b"\r\n", index)
            if line_end != -1:
                break
            ensure(len(body) + 1)

        chunk_size_line = bytes(body[index:line_end]).split(b";", 1)[0].strip()
        try:
            chunk_size = int(chunk_size_line, 16)
        except ValueError as exc:
            raise RuntimeError("Malformed chunked response from benchmark target") from exc

        index = line_end + 2
        ensure(index + chunk_size + 2)

        index += chunk_size
        if body[index : index + 2] != b"\r\n":
            raise RuntimeError("Malformed chunk delimiter in benchmark response")
        index += 2

        if chunk_size == 0:
            return


def _run_http(port: int, requests: int, concurrency: int) -> tuple[int, float]:
    completed_total = 0
    lock = threading.Lock()
    errors: list[Exception] = []
    errors_lock = threading.Lock()

    per_worker = requests // concurrency
    remainder = requests % concurrency

    def worker(work: int) -> None:
        nonlocal completed_total
        try:
            completed = _http_worker(port, work)
        except Exception as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)
            return
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

    if errors:
        raise RuntimeError(f"HTTP benchmark worker failed: {errors[0]}") from errors[0]

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
    with _create_connection_with_retry("127.0.0.1", port, timeout=5) as sock:
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
    errors: list[Exception] = []
    errors_lock = threading.Lock()

    def worker() -> None:
        nonlocal completed_total
        try:
            completed = _ws_worker(port, messages_per_client)
        except Exception as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)
            return
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

    if errors:
        raise RuntimeError(f"WebSocket benchmark worker failed: {errors[0]}") from errors[0]

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
    results: list[ScenarioResult] = []
    try:
        if http_requests > 0:
            http_ops, http_duration = _run_http(port, http_requests, http_concurrency)
            results.append(
                ScenarioResult(
                    server=server,
                    scenario="http",
                    operations=http_ops,
                    duration_seconds=http_duration,
                )
            )

        if ws_clients > 0 and ws_messages > 0:
            ws_ops, ws_duration = _run_ws(port, ws_clients, ws_messages)
            results.append(
                ScenarioResult(
                    server=server,
                    scenario="websocket",
                    operations=ws_ops,
                    duration_seconds=ws_duration,
                )
            )
    finally:
        _stop_server(process)

    return results


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


def _aggregate_results(results: list[ScenarioResult]) -> list[ScenarioResult]:
    grouped: dict[tuple[str, str], list[ScenarioResult]] = {}
    for result in results:
        grouped.setdefault((result.server, result.scenario), []).append(result)

    aggregated: list[ScenarioResult] = []
    for (server, scenario), samples in sorted(grouped.items(), key=lambda entry: entry[0]):
        operations = sum(sample.operations for sample in samples)
        duration = sum(sample.duration_seconds for sample in samples)
        aggregated.append(
            ScenarioResult(
                server=server,
                scenario=scenario,
                operations=operations,
                duration_seconds=duration,
            )
        )
    return aggregated


def _sample_statistics(results: list[ScenarioResult]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[ScenarioResult]] = {}
    for result in results:
        grouped.setdefault((result.scenario, result.server), []).append(result)

    summary: dict[str, dict[str, dict[str, Any]]] = {}
    for (scenario, server), samples in sorted(grouped.items()):
        stats = _compute_statistics([sample.ops_per_second for sample in samples])
        summary.setdefault(scenario, {})[server] = {
            "samples": len(samples),
            "mean": stats["mean"],
            "median": stats["median"],
            "p99": stats["p99"],
            "stddev": stats["stddev"],
            "ci_lower": stats["ci_lower"],
            "ci_upper": stats["ci_upper"],
        }

    for _scenario, by_server in summary.items():
        palfrey = by_server.get("palfrey")
        uvicorn = by_server.get("uvicorn")
        if palfrey is not None and uvicorn is not None and uvicorn["mean"] > 0:
            by_server["ratio"] = {
                "palfrey_over_uvicorn_mean": palfrey["mean"] / uvicorn["mean"],
            }

    return summary


def _capture_metadata() -> dict[str, str]:
    try:
        loop_type = "uvloop" if "uvloop" in sys.modules else "asyncio"
    except Exception:  # noqa: BLE001
        loop_type = "unknown"

    try:
        cpu_info = platform.processor() or platform.machine() or "unknown"
    except Exception:  # noqa: BLE001
        cpu_info = "unknown"

    return {
        "python_version": platform.python_version(),
        "os": platform.system(),
        "cpu": cpu_info,
        "loop_type": loop_type,
    }


def _compute_statistics(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p99": 0.0,
            "stddev": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
        }

    mean_val = statistics.mean(samples)
    median_val = statistics.median(samples)

    if len(samples) < 2:
        stddev_val = 0.0
        p99_val = samples[0]
    else:
        stddev_val = statistics.stdev(samples)
        quantiles = statistics.quantiles(samples, n=100)
        p99_val = quantiles[-1] if quantiles else samples[-1]

    n = len(samples)
    stderr = stddev_val / math.sqrt(n) if n > 0 else 0.0
    margin = 1.96 * stderr

    return {
        "mean": mean_val,
        "median": median_val,
        "p99": p99_val,
        "stddev": stddev_val,
        "ci_lower": mean_val - margin,
        "ci_upper": mean_val + margin,
    }


def _save_json_output(data: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def _run_benchmark_phases(
    server: str,
    port: int,
    http_requests: int,
    http_concurrency: int,
    ws_clients: int,
    ws_messages: int,
    sample_count: int = 1,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")

    primer_requests = min(1000, http_requests // 10)
    warmup_requests = min(5000, http_requests // 2)

    primer_ws_messages = min(100, ws_messages // 10) if ws_clients > 0 else 0
    warmup_ws_messages = min(500, ws_messages // 2) if ws_clients > 0 else 0

    results: dict[str, Any] = {
        "measure_samples": [],
        "http": None,
        "websocket": None,
    }

    if http_requests > 0:
        print(f"Phase: PRIMER (HTTP {primer_requests} requests)")
        _run_http(port, primer_requests, http_concurrency)

        print(f"Phase: WARMUP (HTTP {warmup_requests} requests)")
        _run_http(port, warmup_requests, http_concurrency)

        http_samples: list[ScenarioResult] = []
        for sample_index in range(sample_count):
            sample_label = f", sample {sample_index + 1}/{sample_count}" if sample_count > 1 else ""
            print(f"Phase: MEASURE (HTTP {http_requests} requests{sample_label})")
            http_ops, http_duration = _run_http(port, http_requests, http_concurrency)
            http_samples.append(
                ScenarioResult(
                    server=server,
                    scenario="http",
                    operations=http_ops,
                    duration_seconds=http_duration,
                )
            )
            results["measure_samples"].append(
                http_ops / http_duration if http_duration > 0 else 0.0
            )

        http_aggregate = _aggregate_results(http_samples)[0]
        results["http"] = {
            "operations": http_aggregate.operations,
            "duration_seconds": http_aggregate.duration_seconds,
            "ops_per_second": http_aggregate.ops_per_second,
            "samples": [_result_to_dict(sample) for sample in http_samples],
            "statistics": _sample_statistics(http_samples)["http"][server],
        }

    if ws_clients > 0 and ws_messages > 0:
        print(f"Phase: PRIMER (WS {primer_ws_messages} messages)")
        _run_ws(port, ws_clients, primer_ws_messages)

        print(f"Phase: WARMUP (WS {warmup_ws_messages} messages)")
        _run_ws(port, ws_clients, warmup_ws_messages)

        ws_samples: list[ScenarioResult] = []
        for sample_index in range(sample_count):
            sample_label = f", sample {sample_index + 1}/{sample_count}" if sample_count > 1 else ""
            print(f"Phase: MEASURE (WS {ws_messages} messages{sample_label})")
            ws_ops, ws_duration = _run_ws(port, ws_clients, ws_messages)
            ws_samples.append(
                ScenarioResult(
                    server=server,
                    scenario="websocket",
                    operations=ws_ops,
                    duration_seconds=ws_duration,
                )
            )
            results["measure_samples"].append(ws_ops / ws_duration if ws_duration > 0 else 0.0)

        ws_aggregate = _aggregate_results(ws_samples)[0]
        results["websocket"] = {
            "operations": ws_aggregate.operations,
            "duration_seconds": ws_aggregate.duration_seconds,
            "ops_per_second": ws_aggregate.ops_per_second,
            "samples": [_result_to_dict(sample) for sample in ws_samples],
            "statistics": _sample_statistics(ws_samples)["websocket"][server],
        }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-requests", type=int, default=2000)
    parser.add_argument("--http-concurrency", type=int, default=20)
    parser.add_argument("--ws-clients", type=int, default=1)
    parser.add_argument("--ws-messages", type=int, default=1000)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--enable-phases", action="store_true", default=False)
    parser.add_argument("--samples", type=int, default=1)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be at least 1")

    output_path = args.output or args.json_output
    metadata = _capture_metadata()

    if args.enable_phases:
        print("\n=== 3-Phase Benchmark Mode ===")
        print(f"Python: {metadata['python_version']}")
        print(f"OS: {metadata['os']}")
        print(f"CPU: {metadata['cpu']}")
        print(f"Loop: {metadata['loop_type']}\n")

    results: list[ScenarioResult] = []
    all_phase_results: dict[str, dict[str, Any]] = {}
    servers = ("uvicorn", "palfrey")

    if args.enable_phases:
        for server in servers:
            try:
                port = _available_port()
                process = _spawn_server(server, port)
                try:
                    print(f"\n--- {server.upper()} ---")
                    phase_results = _run_benchmark_phases(
                        server=server,
                        port=port,
                        http_requests=args.http_requests,
                        http_concurrency=args.http_concurrency,
                        ws_clients=args.ws_clients,
                        ws_messages=args.ws_messages,
                        sample_count=args.samples,
                    )
                    all_phase_results[server] = phase_results

                    if phase_results["http"]:
                        results.append(
                            ScenarioResult(
                                server=server,
                                scenario="http",
                                operations=phase_results["http"]["operations"],
                                duration_seconds=phase_results["http"]["duration_seconds"],
                            )
                        )

                    if phase_results["websocket"]:
                        results.append(
                            ScenarioResult(
                                server=server,
                                scenario="websocket",
                                operations=phase_results["websocket"]["operations"],
                                duration_seconds=phase_results["websocket"]["duration_seconds"],
                            )
                        )
                finally:
                    _stop_server(process)
            except Exception as exc:  # noqa: BLE001
                print(f"Benchmark for {server} failed: {exc}")
    else:
        for sample_index in range(args.samples):
            for server in servers:
                try:
                    if args.samples > 1:
                        print(
                            f"\n--- {server.upper()} sample {sample_index + 1}/{args.samples} ---"
                        )
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

    display_results = _aggregate_results(results)
    print("\n| Scenario | Server | Operations | Duration (s) | Ops/s |")
    print("| --- | --- | ---: | ---: | ---: |")
    for result in sorted(display_results, key=lambda entry: (entry.scenario, entry.server)):
        print(
            f"| {result.scenario} | {result.server} | {result.operations} | "
            f"{result.duration_seconds:.4f} | {result.ops_per_second:.2f} |"
        )

    for scenario in ("http", "websocket"):
        ratio = _relative_ratio(display_results, scenario)
        if ratio is None:
            print(f"- {scenario}: n/a")
        else:
            print(f"- {scenario}: {ratio:.3f}x (Palfrey / Uvicorn)")

    if args.samples > 1 and results:
        print("\n=== Sample Statistics ===")
        print("| Scenario | Server | Samples | Mean Ops/s | Median | Stddev |")
        print("| --- | --- | ---: | ---: | ---: | ---: |")
        sample_stats = _sample_statistics(results)
        for scenario, by_server in sample_stats.items():
            for server, stats in by_server.items():
                if server == "ratio":
                    continue
                print(
                    f"| {scenario} | {server} | {stats['samples']} | "
                    f"{stats['mean']:.2f} | {stats['median']:.2f} | {stats['stddev']:.2f} |"
                )

    if args.enable_phases and all_phase_results:
        print("\n=== Statistical Summary ===")
        for server, phase_data in all_phase_results.items():
            print(f"\n{server.upper()}:")
            for scenario in ("http", "websocket"):
                if phase_data.get(scenario):
                    data = phase_data[scenario]
                    ops_s = data["ops_per_second"]
                    stats = data["statistics"]
                    print(f"  {scenario}:")
                    print(f"    ops/s: {ops_s:.2f}")
                    print(f"    stddev: {stats['stddev']:.2f}")

    if output_path is not None:
        if args.enable_phases:
            output_data = {
                "metadata": metadata,
                "results": {
                    server: {
                        "http": phase_data.get("http"),
                        "websocket": phase_data.get("websocket"),
                    }
                    for server, phase_data in all_phase_results.items()
                },
            }
            _save_json_output(output_data, output_path)
        else:
            if args.samples == 1:
                output_payload: Any = [_result_to_dict(result) for result in results]
            else:
                output_payload = {
                    "metadata": metadata,
                    "samples": args.samples,
                    "results": [_result_to_dict(result) for result in results],
                    "summary": _sample_statistics(results),
                }
            output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
