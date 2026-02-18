"""Protocol utility parity tests adapted from Uvicorn patterns."""

from __future__ import annotations

import socket
from asyncio import Transport
from typing import Any

import pytest

from palfrey.protocols.utils import (
    get_client_addr,
    get_local_addr,
    get_path_with_query_string,
    get_remote_addr,
    is_ssl,
)


class MockSocket:
    def __init__(
        self,
        family: socket.AddressFamily,
        *,
        peername: tuple[str, int] | None = None,
        sockname: tuple[str, int] | str | None = None,
    ) -> None:
        self.peername = peername
        self.sockname = sockname
        self.family = family

    def getpeername(self):
        return self.peername

    def getsockname(self):
        return self.sockname


class MockTransport(Transport):
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return self.info.get(name, default)


def test_get_local_addr_with_socket() -> None:
    transport = MockTransport({"socket": MockSocket(family=socket.AF_IPX)})
    assert get_local_addr(transport) is None

    transport = MockTransport({"socket": MockSocket(family=socket.AF_INET6, sockname=("::1", 123))})
    assert get_local_addr(transport) == ("::1", 123)

    transport = MockTransport(
        {"socket": MockSocket(family=socket.AF_INET, sockname=("123.45.6.7", 123))}
    )
    assert get_local_addr(transport) == ("123.45.6.7", 123)

    transport = MockTransport(
        {"socket": MockSocket(family=socket.AF_INET, sockname="/tmp/test.sock")}
    )
    assert get_local_addr(transport) == ("/tmp/test.sock", None)


def test_get_remote_addr_with_socket() -> None:
    transport = MockTransport({"socket": MockSocket(family=socket.AF_IPX)})
    assert get_remote_addr(transport) is None

    transport = MockTransport({"socket": MockSocket(family=socket.AF_INET6, peername=("::1", 123))})
    assert get_remote_addr(transport) == ("::1", 123)

    transport = MockTransport(
        {"socket": MockSocket(family=socket.AF_INET, peername=("123.45.6.7", 123))}
    )
    assert get_remote_addr(transport) == ("123.45.6.7", 123)


def test_get_local_addr() -> None:
    transport = MockTransport({"sockname": "path/to/unix-domain-socket"})
    assert get_local_addr(transport) == ("path/to/unix-domain-socket", None)

    transport = MockTransport({"sockname": ("123.45.6.7", 123)})
    assert get_local_addr(transport) == ("123.45.6.7", 123)

    transport = MockTransport({})
    assert get_local_addr(transport) is None


def test_get_remote_addr() -> None:
    transport = MockTransport({"peername": None})
    assert get_remote_addr(transport) is None

    transport = MockTransport({"peername": ("123.45.6.7", 123)})
    assert get_remote_addr(transport) == ("123.45.6.7", 123)


@pytest.mark.parametrize(
    ("scope", "expected_client"),
    [({"client": ("127.0.0.1", 36000)}, "127.0.0.1:36000"), ({"client": None}, "")],
    ids=["ip:port client", "None client"],
)
def test_get_client_addr_value(scope: dict[str, Any], expected_client: str) -> None:
    assert get_client_addr(scope) == expected_client


def test_is_ssl_reads_sslcontext_flag() -> None:
    assert is_ssl(MockTransport({"sslcontext": object()})) is True
    assert is_ssl(MockTransport({"sslcontext": None})) is False


def test_get_path_with_query_string_quotes_and_appends_query() -> None:
    scope = {"path": "/one two", "query_string": b"x=1"}
    assert get_path_with_query_string(scope) == "/one%20two?x=1"


def test_get_path_with_query_string_without_query() -> None:
    scope = {"path": "/ok", "query_string": b""}
    assert get_path_with_query_string(scope) == "/ok"
