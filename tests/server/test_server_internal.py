"""Internal server behavior tests."""

from __future__ import annotations

import asyncio

from palfrey.config import PalfreyConfig
from palfrey.server import PalfreyServer


def test_normalize_address_from_tuple() -> None:
    host, port = PalfreyServer._normalize_address(
        ("127.0.0.1", 8000),
        default_host="x",
        default_port=1,
    )
    assert host == "127.0.0.1"
    assert port == 8000


def test_normalize_address_uses_defaults_for_unknown_type() -> None:
    host, port = PalfreyServer._normalize_address(
        "not-a-tuple",
        default_host="x",
        default_port=1,
    )
    assert host == "x"
    assert port == 1


def test_request_slot_limit_enforced() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", limit_concurrency=1)
    server = PalfreyServer(config)

    async def scenario() -> None:
        assert await server._enter_request_slot() is True
        assert await server._enter_request_slot() is False
        await server._leave_request_slot()
        assert await server._enter_request_slot() is True
        await server._leave_request_slot()

    asyncio.run(scenario())
