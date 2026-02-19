from __future__ import annotations

import errno
import socket

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


def test_run_ws_raises_when_worker_thread_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ws_worker(port: int, messages: int) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(bench_run, "_ws_worker", fake_ws_worker)

    with pytest.raises(RuntimeError, match="WebSocket benchmark worker failed: boom"):
        bench_run._run_ws(port=8000, clients=2, messages_per_client=10)


def test_build_command_uses_optimized_profiles() -> None:
    palfrey_cmd = bench_run._build_command("palfrey", 8123)
    uvicorn_cmd = bench_run._build_command("uvicorn", 8123)

    assert "--no-access-log" in palfrey_cmd
    assert "--no-access-log" in uvicorn_cmd

    assert palfrey_cmd[palfrey_cmd.index("--http") + 1] == "httptools"
    assert uvicorn_cmd[uvicorn_cmd.index("--http") + 1] == "h11"

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
