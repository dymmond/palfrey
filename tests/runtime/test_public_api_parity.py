"""Public API parity tests for top-level package exports."""

from __future__ import annotations

import palfrey
from palfrey.cli import main as cli_main
from palfrey.config import PalfreyConfig
from palfrey.runtime import run as runtime_run
from palfrey.server import PalfreyServer


def test_package_exports_uvicorn_compatible_names() -> None:
    assert palfrey.Config is PalfreyConfig
    assert palfrey.Server is PalfreyServer
    assert palfrey.main is cli_main
    assert palfrey.run is runtime_run
