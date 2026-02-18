"""Parity tests for ``palfrey.main`` module exports."""

from __future__ import annotations

import importlib

from palfrey.server import ServerState


def test_main_module_exposes_server_state_attr() -> None:
    module = importlib.import_module("palfrey.main")
    assert module.ServerState is ServerState
