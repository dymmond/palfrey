from __future__ import annotations

import errno
import json
import socket
from pathlib import Path

import pytest

from benchmarks import run as bench_run


def test_create_connection_with_retry_retries_retryable_errno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def fake_create_connection(address: tuple[str, int], timeout: float = 5.0) -> socket.socket:
        attempts["count"] += 1
        assert address == ("127.0.0.1", 8000)
        assert timeout == 1.0
        if attempts["count"] < 3:
            raise OSError(errno.EADDRNOTAVAIL, "Can't assign requested address")
        return probe_socket

    monkeypatch.setattr(bench_run.socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(bench_run.time, "sleep", lambda value: sleep_calls.append(value))
    monkeypatch.setattr(bench_run.random, "random", lambda: 0.0)

    conn = bench_run._create_connection_with_retry(
        "127.0.0.1",
        8000,
        timeout=1.0,
        attempts=5,
        initial_backoff=0.01,
        max_backoff=0.1,
    )
    try:
        assert conn is probe_socket
        assert attempts["count"] == 3
        assert sleep_calls == [0.01, 0.02]
    finally:
        conn.close()


def test_create_connection_with_retry_raises_non_retryable_errno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_connection(address: tuple[str, int], timeout: float = 5.0) -> socket.socket:
        raise OSError(errno.ECONNREFUSED, "Connection refused")

    monkeypatch.setattr(bench_run.socket, "create_connection", fake_create_connection)

    with pytest.raises(OSError) as exc_info:
        bench_run._create_connection_with_retry("127.0.0.1", 8000, attempts=3)

    assert exc_info.value.errno == errno.ECONNREFUSED


def test_run_http_raises_when_worker_thread_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_worker(port: int, requests: int) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(bench_run, "_http_worker", fake_http_worker)

    with pytest.raises(RuntimeError, match="HTTP benchmark worker failed: boom"):
        bench_run._run_http(port=8000, requests=10, concurrency=2)


def test_run_http_collects_latency_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_worker(port: int, requests: int) -> bench_run.OperationRun:
        return bench_run.OperationRun(
            operations=requests,
            duration_seconds=0.1,
            latency_seconds=tuple(0.01 for _ in range(requests)),
        )

    monkeypatch.setattr(bench_run, "_http_worker", fake_http_worker)

    measurement = bench_run._run_http(port=8000, requests=5, concurrency=2)

    assert measurement.operations == 5
    assert len(measurement.latency_seconds) == 5


def test_run_ws_raises_when_worker_thread_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ws_worker(port: int, messages: int) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(bench_run, "_ws_worker", fake_ws_worker)

    with pytest.raises(RuntimeError, match="WebSocket benchmark worker failed: boom"):
        bench_run._run_ws(port=8000, clients=2, messages_per_client=10)


def test_run_ws_collects_latency_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ws_worker(port: int, messages: int) -> bench_run.OperationRun:
        return bench_run.OperationRun(
            operations=messages,
            duration_seconds=0.1,
            latency_seconds=tuple(0.02 for _ in range(messages)),
        )

    monkeypatch.setattr(bench_run, "_ws_worker", fake_ws_worker)

    measurement = bench_run._run_ws(port=8000, clients=3, messages_per_client=4)

    assert measurement.operations == 12
    assert len(measurement.latency_seconds) == 12


def test_build_command_uses_optimized_profiles() -> None:
    palfrey_cmd = bench_run._build_command("palfrey", 8123)
    uvicorn_cmd = bench_run._build_command("uvicorn", 8123)

    assert "--no-access-log" in palfrey_cmd
    assert "--no-access-log" in uvicorn_cmd
    assert "--no-proxy-headers" in palfrey_cmd
    assert "--no-proxy-headers" in uvicorn_cmd

    assert palfrey_cmd[palfrey_cmd.index("--http") + 1] == "auto"
    assert uvicorn_cmd[uvicorn_cmd.index("--http") + 1] == "httptools"

    assert palfrey_cmd[palfrey_cmd.index("--ws") + 1] == "websockets"
    assert uvicorn_cmd[uvicorn_cmd.index("--ws") + 1] == "websockets"


def test_build_command_uses_current_interpreter_when_python_env_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTHON", raising=False)
    command = bench_run._build_command("palfrey", 8123)
    assert command[0] == bench_run.sys.executable


def test_build_command_allows_python_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHON", "/tmp/custom-python")
    command = bench_run._build_command("uvicorn", 8123)
    assert command[0] == "/tmp/custom-python"


def test_benchmark_server_skips_disabled_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_counts = {"http": 0, "ws": 0, "stop": 0}
    fake_process = object()

    monkeypatch.setattr(bench_run, "_available_port", lambda: 8123)
    monkeypatch.setattr(bench_run, "_spawn_server", lambda server, port: fake_process)

    def fake_stop(process: object) -> None:
        assert process is fake_process
        call_counts["stop"] += 1

    def fake_http(port: int, requests: int, concurrency: int) -> tuple[int, float]:
        call_counts["http"] += 1
        return (requests, 0.1)

    def fake_ws(port: int, clients: int, messages: int) -> tuple[int, float]:
        call_counts["ws"] += 1
        return (clients * messages, 0.1)

    monkeypatch.setattr(bench_run, "_stop_server", fake_stop)
    monkeypatch.setattr(bench_run, "_run_http", fake_http)
    monkeypatch.setattr(bench_run, "_run_ws", fake_ws)

    results = bench_run._benchmark_server(
        "palfrey",
        http_requests=0,
        http_concurrency=20,
        ws_clients=0,
        ws_messages=50,
    )

    assert results == []
    assert call_counts == {"http": 0, "ws": 0, "stop": 1}


def test_benchmark_server_attaches_process_resource_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_process = object()
    snapshots = [
        bench_run.ProcessResources(cpu_time_seconds=1.0, rss_bytes=100),
        bench_run.ProcessResources(cpu_time_seconds=1.75, rss_bytes=150),
    ]

    monkeypatch.setattr(bench_run, "_available_port", lambda: 8123)
    monkeypatch.setattr(bench_run, "_spawn_server", lambda server, port: fake_process)
    monkeypatch.setattr(bench_run, "_stop_server", lambda process: None)
    monkeypatch.setattr(bench_run, "_capture_process_resources", lambda process: snapshots.pop(0))
    monkeypatch.setattr(
        bench_run,
        "_run_http",
        lambda port, requests, concurrency: bench_run.OperationRun(
            operations=requests,
            duration_seconds=0.25,
            latency_seconds=(0.01,),
        ),
    )

    results = bench_run._benchmark_server(
        "palfrey",
        http_requests=10,
        http_concurrency=2,
        ws_clients=0,
        ws_messages=0,
    )

    assert results[0].cpu_time_seconds == pytest.approx(0.75)
    assert results[0].max_rss_bytes == 150


def test_main_samples_repeats_simple_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    output_path = tmp_path / "benchmark.json"

    monkeypatch.setattr(
        bench_run.sys,
        "argv",
        [
            "run.py",
            "--http-requests",
            "100",
            "--ws-clients",
            "0",
            "--samples",
            "3",
            "--output",
            str(output_path),
        ],
    )

    def fake_benchmark_server(server: str, **kwargs: object) -> list[bench_run.ScenarioResult]:
        calls.append(server)
        return [bench_run.ScenarioResult(server, "http", 100, 0.5)]

    monkeypatch.setattr(bench_run, "_benchmark_server", fake_benchmark_server)

    bench_run.main()

    assert calls == ["uvicorn", "palfrey", "uvicorn", "palfrey", "uvicorn", "palfrey"]
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["samples"] == 3
    assert payload["summary"]["http"]["palfrey"]["samples"] == 3


def test_main_rejects_zero_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bench_run.sys, "argv", ["run.py", "--samples", "0"])

    with pytest.raises(SystemExit):
        bench_run.main()
