"""Runtime orchestration tests."""

from __future__ import annotations

import pytest

from palfrey.config import PalfreyConfig
from palfrey.runtime import _configure_loop, _run_config


def test_configure_loop_rejects_unsupported_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported loop mode"):
        _configure_loop("invalid")


def test_run_config_rejects_reload_and_workers_together() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=True, workers=2)
    with pytest.raises(RuntimeError, match="cannot be used together"):
        _run_config(config)


def test_run_config_rejects_reload_for_non_import_app() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, reload=True)
    with pytest.raises(RuntimeError, match="requires the application to be an import string"):
        _run_config(config)


def test_run_config_rejects_workers_for_non_import_app() -> None:
    async def app(scope, receive, send):
        return None

    config = PalfreyConfig(app=app, workers=2)
    with pytest.raises(RuntimeError, match="requires the application to be an import string"):
        _run_config(config)
