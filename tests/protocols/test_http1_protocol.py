from __future__ import annotations

import asyncio
from typing import Any

import pytest

from palfrey.config import PalfreyConfig
from palfrey.protocols.http1 import PalfreyHTTPProtocol
from palfrey.server import ServerState


class _Socket:
    def __init__(self) -> None:
        self.options: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, optname: int, value: int) -> None:
        self.options.append((level, optname, value))


class _Transport(asyncio.Transport):
    def __init__(
        self,
        *,
        peername: Any = ("127.0.0.1", 50123),
        sockname: Any = ("127.0.0.1", 8000),
        socket: Any = None,
        ssl_object: Any = None,
    ) -> None:
        super().__init__()
        self.writes: list[bytes] = []
        self.closed = False
        self.peername = peername
        self.sockname = sockname
        self.socket = socket
        self.ssl_object = ssl_object

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        if name == "peername":
            return self.peername
        if name == "sockname":
            return self.sockname
        if name == "socket":
            return self.socket
        if name == "ssl_object":
            return self.ssl_object
        return default


async def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached before timeout")


def _loaded_config(app: str = "tests.fixtures.apps:http_app", **kwargs: Any) -> PalfreyConfig:
    config = PalfreyConfig(app=app, **kwargs)
    config.load()
    return config


def test_http1_protocol_serves_pipelined_keep_alive_requests() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(timeout_keep_alive=60),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(
            b"GET /one HTTP/1.1\r\nHost: example.com\r\nConnection: keep-alive\r\n\r\n"
            b"GET /two HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"
        )

        await _wait_for(lambda: transport.closed)
        payload = b"".join(transport.writes)
        assert payload.count(b"HTTP/1.1 200 OK") == 2
        assert payload.count(b"ok") == 2
        assert protocol.server_state.total_requests == 2

    asyncio.run(scenario())


def test_http1_protocol_closes_idle_keep_alive_connection() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(timeout_keep_alive=0.001),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")

        await _wait_for(lambda: bool(transport.writes))
        assert transport.closed is False
        await _wait_for(lambda: transport.closed)

    asyncio.run(scenario())


def test_http1_protocol_rejects_unsupported_chunked_request_body() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(
            b"POST / HTTP/1.1\r\nHost: example.com\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        )

        await _wait_for(lambda: transport.closed)
        payload = b"".join(transport.writes)
        assert b"501 Not Implemented" in payload

    asyncio.run(scenario())


def test_http1_protocol_sets_socket_options_and_scope_metadata() -> None:
    async def scenario() -> None:
        sock = _Socket()
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(app="tests.fixtures.apps:http_scope_echo_app"),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport(
            peername=("198.51.100.8", 50123),
            sockname=("203.0.113.10", 443),
            socket=sock,
            ssl_object=object(),
        )
        protocol.connection_made(transport)

        protocol.data_received(b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")

        await _wait_for(lambda: transport.closed)
        payload = b"".join(transport.writes)
        assert sock.options
        assert b"scheme=https;client=198.51.100.8" in payload

    asyncio.run(scenario())


def test_http1_protocol_sends_100_continue_and_body_to_app() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(app="tests.fixtures.apps:http_expect_continue_body_app"),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(
            b"POST / HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Length: 5\r\n"
            b"Expect: 100-continue\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"hello"
        )

        await _wait_for(lambda: transport.closed)
        payload = b"".join(transport.writes)
        assert b"HTTP/1.1 100 Continue" in payload
        assert b"Body: hello" in payload

    asyncio.run(scenario())


def test_http1_protocol_waits_for_incomplete_request_body() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(app="tests.fixtures.apps:http_expect_continue_body_app"),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(
            b"POST / HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Length: 5\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"he"
        )

        assert transport.writes == []
        protocol.data_received(b"llo")

        await _wait_for(lambda: transport.closed)
        assert b"Body: hello" in b"".join(transport.writes)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("request_bytes", "status"),
    [
        (b"GET\r\n\r\n", b"400 Bad Request"),
        (b"G" * 1_048_577, b"400 Bad Request"),
        (
            b"POST / HTTP/1.1\r\nHost: example.com\r\nContent-Length: nope\r\n\r\n",
            b"400 Bad Request",
        ),
        (b"POST / HTTP/1.1\r\nHost: example.com\r\nContent-Length: -1\r\n\r\n", b"400 Bad Request"),
        (
            b"POST / HTTP/1.1\r\nHost: example.com\r\nContent-Length: 4194305\r\n\r\n",
            b"400 Bad Request",
        ),
        (
            b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n",
            b"400 Bad Request",
        ),
    ],
)
def test_http1_protocol_rejects_invalid_request_framing(
    request_bytes: bytes, status: bytes
) -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(request_bytes)

        await _wait_for(lambda: transport.closed)
        assert status in b"".join(transport.writes)

    asyncio.run(scenario())


def test_http1_protocol_rejects_requests_when_concurrency_limit_is_reached() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(limit_concurrency=1),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")

        await _wait_for(lambda: transport.closed)
        assert b"503 Service Unavailable" in b"".join(transport.writes)

    asyncio.run(scenario())


def test_http1_protocol_closes_after_request_limit() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(limit_max_requests=1, timeout_keep_alive=60),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(
            b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: keep-alive\r\n\r\n"
        )

        await _wait_for(lambda: transport.closed)
        assert protocol.server_state.total_requests == 1
        assert b"200 OK" in b"".join(transport.writes)

    asyncio.run(scenario())


def test_http1_protocol_cleans_up_active_task_on_connection_lost() -> None:
    async def scenario() -> None:
        state = ServerState()
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(app="tests.fixtures.apps:http_slow_response_app"),
            server_state=state,
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport()
        protocol.connection_made(transport)

        protocol.data_received(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await _wait_for(lambda: protocol.active_task is not None)

        task = protocol.active_task
        protocol.connection_lost(None)
        await asyncio.sleep(0)

        assert task is not None
        assert task.cancelled()
        assert protocol not in state.connections
        assert task not in state.tasks

    asyncio.run(scenario())


def test_http1_protocol_eof_and_default_addresses() -> None:
    async def scenario() -> None:
        protocol = PalfreyHTTPProtocol(
            config=_loaded_config(),
            server_state=ServerState(),
            _loop=asyncio.get_running_loop(),
        )
        transport = _Transport(peername=None, sockname=None)

        protocol.connection_made(transport)

        assert protocol.eof_received() is None
        assert protocol.client == ("0.0.0.0", 0)
        assert protocol.server == ("127.0.0.1", 8000)

    asyncio.run(scenario())
