from __future__ import annotations

from pathlib import Path

import pytest

from palfrey.config import PalfreyConfig


@pytest.mark.parametrize(
    ("app", "expected"),
    [
        ("tests.fixtures.apps:http_app", True),
        (lambda scope, receive, send: None, False),
    ],
)
def test_config_should_reload_depends_on_import_string(app, expected: bool) -> None:
    config = PalfreyConfig(app=app, reload=True)
    assert config.should_reload is expected


def test_config_warns_when_reload_options_are_set_without_reload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    PalfreyConfig(app="tests.fixtures.apps:http_app", reload_dirs=[str(tmp_path)])
    assert "Current configuration will not reload as not all conditions are met" in caplog.text


@pytest.mark.parametrize(
    ("reload", "workers", "expected"),
    [(False, 1, False), (True, 1, True), (False, 2, True)],
)
def test_config_use_subprocess_property(reload: bool, workers: int, expected: bool) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", reload=reload, workers=workers)
    assert config.use_subprocess is expected


@pytest.mark.parametrize(
    ("interface", "expected"),
    [("asgi2", "2.0"), ("asgi3", "3.0"), ("wsgi", "3.0")],
)
def test_config_asgi_version_mapping(interface: str, expected: str) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", interface=interface)
    assert config.asgi_version == expected
