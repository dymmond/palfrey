from __future__ import annotations

import logging

import pytest

from palfrey.runtime import STARTUP_FAILURE, run


def test_run_invalid_app_config_combination_exits_with_status_1() -> None:
    async def app(scope, receive, send):
        return None

    messages: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    runtime_logger = logging.getLogger("palfrey.runtime")
    capture_handler = _CaptureHandler()
    runtime_logger.addHandler(capture_handler)
    with pytest.raises(SystemExit) as exc_info:
        try:
            run(app, reload=True)
        finally:
            runtime_logger.removeHandler(capture_handler)
    assert exc_info.value.code == 1
    assert any(
        "You must pass the application as an import string" in message for message in messages
    )


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
