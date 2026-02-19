from __future__ import annotations

from palfrey.config import PalfreyConfig


def test_normalized_headers_accept_tuple_values() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=[("x-test", "yes")])
    assert config.normalized_headers == [("x-test", "yes")]


def test_normalized_headers_accept_string_values() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", headers=["x-test: yes"])
    assert config.normalized_headers == [("x-test", "yes")]
