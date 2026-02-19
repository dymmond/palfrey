from __future__ import annotations

from importlib.machinery import ModuleSpec

import pytest

import palfrey.config as config_module
from palfrey.config import PalfreyConfig


def test_config_accepts_custom_loop_import_string() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        loop="tests.loops.custom_loop_factory:setup_loop",
    )
    assert config.loop == "tests.loops.custom_loop_factory:setup_loop"


def test_config_normalizes_uppercase_mode_values() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        http="H11",
        ws="WebSockets",
        lifespan="AUTO",
        interface="ASGI3",
    )
    assert config.http == "h11"
    assert config.ws == "websockets"
    assert config.lifespan == "auto"
    assert config.interface == "asgi3"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("http", "invalid-http", "Unsupported HTTP mode"),
        ("ws", "invalid-ws", "Unsupported WebSocket mode"),
        ("lifespan", "invalid-lifespan", "Unsupported lifespan mode"),
        ("interface", "invalid-interface", "Unsupported interface mode"),
    ],
)
def test_config_rejects_unsupported_runtime_modes(field: str, value: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        PalfreyConfig(app="tests.fixtures.apps:http_app", **{field: value})


def test_config_rejects_invalid_loop_without_import_separator() -> None:
    with pytest.raises(ValueError, match="Unsupported loop mode"):
        PalfreyConfig(app="tests.fixtures.apps:http_app", loop="invalid-loop")


def test_effective_http_resolves_auto_to_httptools_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "find_spec",
        lambda name: ModuleSpec(name, loader=None) if name == "httptools" else None,
    )
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", http="auto")
    assert config.effective_http == "httptools"


def test_effective_http_resolves_auto_to_h11_when_httptools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "find_spec", lambda name: None)
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", http="auto")
    assert config.effective_http == "h11"


def test_effective_ws_resolves_auto_to_websockets_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "find_spec",
        lambda name: ModuleSpec(name, loader=None) if name == "websockets" else None,
    )
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", ws="auto")
    assert config.effective_ws == "websockets"


def test_effective_ws_resolves_auto_to_wsproto_when_websockets_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "find_spec",
        lambda name: ModuleSpec(name, loader=None) if name == "wsproto" else None,
    )
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", ws="auto")
    assert config.effective_ws == "wsproto"


def test_effective_ws_resolves_auto_to_none_when_no_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "find_spec", lambda name: None)
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", ws="auto")
    assert config.effective_ws == "none"


def test_effective_ws_forces_none_for_wsgi_interface() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", interface="wsgi", ws="websockets")
    assert config.effective_ws == "none"


def test_config_accepts_http2_and_http3_modes() -> None:
    config_h2 = PalfreyConfig(app="tests.fixtures.apps:http_app", http="h2")
    config_h3 = PalfreyConfig(app="tests.fixtures.apps:http_app", http="h3")
    assert config_h2.http == "h2"
    assert config_h3.http == "h3"


def test_effective_ws_forces_none_for_http3_mode() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", http="h3", ws="websockets")
    assert config.effective_ws == "none"
