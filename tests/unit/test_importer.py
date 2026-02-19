from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.importer import resolve_application


def test_resolve_asgi3_application() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app")
    resolved = resolve_application(config)
    assert resolved.interface in {"asgi3", "auto"}
    assert callable(resolved.app)


def test_resolve_with_explicit_asgi2_wrapper() -> None:
    class AppV2:
        def __call__(self, scope):
            async def app(receive, send):
                if scope["type"] == "http":
                    await send({"type": "http.response.start", "status": 200, "headers": []})
                    await send({"type": "http.response.body", "body": b"ok"})

            return app

    config = PalfreyConfig(app=AppV2(), interface="asgi2")
    resolved = resolve_application(config)
    assert resolved.interface == "asgi2"
    assert callable(resolved.app)
