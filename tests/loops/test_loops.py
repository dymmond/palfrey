from __future__ import annotations

import asyncio
import types

import pytest

from palfrey.loops import LOOP_SETUPS
from palfrey.loops.asyncio import asyncio_setup
from palfrey.loops.auto import auto_loop_setup
from palfrey.loops.none import none_loop_setup
from palfrey.loops.uvloop import uvloop_setup


def test_loop_setups_exposes_supported_modes() -> None:
    assert set(LOOP_SETUPS) == {"none", "auto", "asyncio", "uvloop"}


def test_none_loop_setup_is_noop() -> None:
    policy_before = asyncio.get_event_loop_policy()
    none_loop_setup()
    assert asyncio.get_event_loop_policy() is policy_before


def test_asyncio_loop_setup_is_noop() -> None:
    policy_before = asyncio.get_event_loop_policy()
    asyncio_setup()
    assert asyncio.get_event_loop_policy() is policy_before


def test_auto_loop_setup_swallows_missing_uvloop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "uvloop":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    auto_loop_setup()  # should not raise


def test_uvloop_setup_sets_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    previous_policy = asyncio.get_event_loop_policy()

    class FakePolicy(asyncio.DefaultEventLoopPolicy):
        pass

    fake_uvloop = types.SimpleNamespace(EventLoopPolicy=FakePolicy)
    monkeypatch.setitem(__import__("sys").modules, "uvloop", fake_uvloop)

    try:
        uvloop_setup()
        assert isinstance(asyncio.get_event_loop_policy(), FakePolicy)
    finally:
        asyncio.set_event_loop_policy(previous_policy)
