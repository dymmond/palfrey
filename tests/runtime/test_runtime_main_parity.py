"""Runtime parity tests aligned with Uvicorn's public run() behavior."""

from __future__ import annotations

import pytest

from palfrey.runtime import STARTUP_FAILURE, run


def test_run_invalid_app_config_combination_exits_with_status_1(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def app(scope, receive, send):
        return None

    with pytest.raises(SystemExit) as exc_info:
        run(app, reload=True)
    assert exc_info.value.code == 1
    assert "You must pass the application as an import string" in caplog.text


def test_run_startup_failure_exits_with_startup_failure_code() -> None:
    async def app(scope, receive, send):
        if scope["type"] != "lifespan":
            return
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.failed", "message": "boom"})

    with pytest.raises(SystemExit) as exc_info:
        run(app, lifespan="on")
    assert exc_info.value.code == STARTUP_FAILURE
