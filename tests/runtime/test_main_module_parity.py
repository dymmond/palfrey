"""Parity tests for ``palfrey.main`` module exports."""

from __future__ import annotations

import importlib

import pytest

from palfrey.config import PalfreyConfig
from palfrey.server import PalfreyServer, ServerState


def test_main_module_exposes_server_state_attr() -> None:
    module = importlib.import_module("palfrey.main")
    with pytest.warns(DeprecationWarning, match="palfrey.main.ServerState is deprecated"):
        assert module.ServerState is ServerState


def test_main_module_exposes_config_and_server_aliases() -> None:
    module = importlib.import_module("palfrey.main")
    assert module.Config is PalfreyConfig
    assert module.Server is PalfreyServer
