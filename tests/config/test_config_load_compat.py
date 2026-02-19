from __future__ import annotations

import pytest

import palfrey.config as config_module
from palfrey.config import PalfreyConfig
from palfrey.lifespan import LifespanManager
from palfrey.middleware.message_logger import MessageLoggerMiddleware
from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware
from tests.config.custom_protocol_classes import DummyHTTPProtocol, DummyWSProtocol


async def _asgi_app(scope, receive, send):
    return None


def _wsgi_app(environ, start_response):
    start_response("200 OK", [("content-type", "text/plain")])
    return [b"ok"]


def test_config_load_sets_loaded_state_and_encoded_headers() -> None:
    config = PalfreyConfig(
        app="tests.fixtures.apps:http_app",
        headers=[("x-test", "1")],
        proxy_headers=False,
    )
    config.load()
    assert config.loaded is True
    assert callable(config.loaded_app)
    assert config.encoded_headers[0] == (b"server", b"palfrey")
    assert (b"x-test", b"1") in config.encoded_headers
    assert config.http_protocol_class in {"h11", "httptools"}
    assert config.ws_protocol_class in {
        "none",
        "websockets",
        "websockets-sansio",
        "wsproto",
    }
    assert config.lifespan_class is LifespanManager


def test_config_load_wsgi_interface_wraps_wsgi_adapter() -> None:
    config = PalfreyConfig(app=_wsgi_app, interface="wsgi", proxy_headers=False)
    config.load()
    assert config.interface == "wsgi"
    assert callable(config.loaded_app)


def test_config_load_proxy_headers_wraps_loaded_app() -> None:
    config = PalfreyConfig(app=_asgi_app, proxy_headers=True)
    config.load()
    assert isinstance(config.loaded_app, ProxyHeadersMiddleware)


def test_config_load_trace_message_logger_wrap_order() -> None:
    config = PalfreyConfig(app=_asgi_app, log_level="trace", proxy_headers=True)
    config.load()
    assert isinstance(config.loaded_app, ProxyHeadersMiddleware)
    assert isinstance(config.loaded_app.app, MessageLoggerMiddleware)


def test_config_load_missing_attribute_exits_with_status_1(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:not_there")
    with pytest.raises(SystemExit) as exc_info:
        config.load()
    assert exc_info.value.code == 1
    assert "Error loading ASGI app." in caplog.text


def test_config_load_factory_type_error_logs_factory_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(app=_asgi_app, factory=True)
    with pytest.raises(SystemExit) as exc_info:
        config.load()
    assert exc_info.value.code == 1
    assert "Error loading ASGI app factory:" in caplog.text


def test_config_load_unimportable_module_propagates_module_not_found() -> None:
    config = PalfreyConfig(app="no.such:app")
    with pytest.raises(ModuleNotFoundError):
        config.load()


def test_config_load_creates_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def fake_create_ssl_context(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(config_module, "create_ssl_context", fake_create_ssl_context)
    config = PalfreyConfig(
        app=_asgi_app,
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
        ssl_keyfile_password="secret",
        ssl_version=777,
        ssl_cert_reqs=1,
        ssl_ca_certs="ca.pem",
        ssl_ciphers="ECDHE",
        proxy_headers=False,
    )

    config.load()
    assert config.ssl_context is sentinel
    assert captured["certfile"] == "cert.pem"
    assert captured["keyfile"] == "key.pem"
    assert captured["password"] == "secret"
    assert captured["ssl_version"] == 777
    assert captured["cert_reqs"] == 1
    assert captured["ca_certs"] == "ca.pem"
    assert captured["ciphers"] == "ECDHE"


def test_config_load_ssl_requires_certfile() -> None:
    config = PalfreyConfig(app=_asgi_app, ssl_keyfile="key.pem", proxy_headers=False)
    with pytest.raises(AssertionError):
        config.load()


def test_config_load_imports_custom_http_protocol_class() -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        http="tests.config.custom_protocol_classes:DummyHTTPProtocol",
        proxy_headers=False,
    )
    config.load()
    assert config.http_protocol_class.__name__ == "DummyHTTPProtocol"


def test_config_load_accepts_concrete_http_protocol_class() -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        http=DummyHTTPProtocol,
        proxy_headers=False,
    )
    config.load()
    assert config.http_protocol_class is DummyHTTPProtocol


def test_config_load_imports_custom_ws_protocol_class() -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        ws="tests.config.custom_protocol_classes:DummyWSProtocol",
        proxy_headers=False,
    )
    config.load()
    assert config.ws_protocol_class.__name__ == "DummyWSProtocol"


def test_config_load_accepts_concrete_ws_protocol_class() -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        ws=DummyWSProtocol,
        proxy_headers=False,
    )
    config.load()
    assert config.ws_protocol_class is DummyWSProtocol


def test_config_load_invalid_custom_http_protocol_class_exits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        http="tests.config.custom_protocol_classes:NotThere",
        proxy_headers=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        config.load()
    assert exc_info.value.code == 1
    assert "Error loading HTTP protocol class." in caplog.text


def test_config_load_invalid_custom_ws_protocol_class_exits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PalfreyConfig(
        app=_asgi_app,
        ws="tests.config.custom_protocol_classes:NotThere",
        proxy_headers=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        config.load()
    assert exc_info.value.code == 1
    assert "Error loading WebSocket protocol class." in caplog.text


def test_config_load_sets_no_lifespan_class_for_off_mode() -> None:
    config = PalfreyConfig(app=_asgi_app, lifespan="off", proxy_headers=False)
    config.load()
    assert config.lifespan_class is None
