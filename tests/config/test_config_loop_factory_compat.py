from __future__ import annotations

import asyncio
from contextlib import closing

import pytest

from palfrey.config import PalfreyConfig


async def _asgi_app(scope, receive, send):
    return None


def test_get_loop_factory_none_returns_none() -> None:
    config = PalfreyConfig(app=_asgi_app, loop="none")
    assert config.get_loop_factory() is None


def test_get_loop_factory_asyncio_returns_event_loop_factory() -> None:
    config = PalfreyConfig(app=_asgi_app, loop="asyncio")
    loop_factory = config.get_loop_factory()
    assert loop_factory is not None
    loop = loop_factory()
    with closing(loop):
        assert isinstance(loop, asyncio.AbstractEventLoop)


def test_get_loop_factory_custom_import_string() -> None:
    config = PalfreyConfig(app=_asgi_app, loop="tests.loops.custom_loop_class:CustomLoop")
    loop_factory = config.get_loop_factory()
    assert loop_factory is not None
    loop = loop_factory()
    with closing(loop):
        assert loop.__class__.__name__ == "CustomLoop"


def test_get_loop_factory_invalid_import_logs_and_exits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(app=_asgi_app, loop="tests.config.test_config_loop_factory_parity:nope")
    with pytest.raises(SystemExit) as exc_info:
        config.get_loop_factory()
    assert exc_info.value.code == 1
    assert "Error loading custom loop setup function." in caplog.text


def test_setup_event_loop_removed_api_raises_attribute_error() -> None:
    config = PalfreyConfig(app=_asgi_app)
    with pytest.raises(
        AttributeError,
        match="The `setup_event_loop` method was replaced by `get_loop_factory` in uvicorn 0.36.0.",
    ):
        config.setup_event_loop()
