"""Custom loop import-string parity tests."""

from __future__ import annotations

import importlib

import pytest

from palfrey.loops import resolve_loop_setup
from palfrey.runtime import _configure_loop


def test_resolve_loop_setup_from_import_string() -> None:
    fixture = importlib.import_module("tests.loops.custom_loop_factory")
    fixture.CALLED = False

    setup = resolve_loop_setup("tests.loops.custom_loop_factory:setup_loop")
    setup()

    assert fixture.CALLED is True


def test_configure_loop_executes_import_string_setup() -> None:
    fixture = importlib.import_module("tests.loops.custom_loop_factory")
    fixture.CALLED = False

    _configure_loop("tests.loops.custom_loop_factory:setup_loop")

    assert fixture.CALLED is True


def test_resolve_loop_setup_rejects_invalid_import_string() -> None:
    with pytest.raises(ValueError, match="Unsupported loop mode"):
        resolve_loop_setup("tests.loops.custom_loop_factory")


def test_resolve_loop_setup_rejects_missing_callable() -> None:
    with pytest.raises(ValueError, match="Unsupported loop mode"):
        resolve_loop_setup("tests.loops.custom_loop_factory:missing")
