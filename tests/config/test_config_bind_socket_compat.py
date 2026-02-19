"""Socket-binding parity tests for parent-process supervision modes."""

from __future__ import annotations

from pathlib import Path

import pytest

import palfrey.config as config_module
from palfrey.config import PalfreyConfig


def test_bind_socket_tcp_marks_socket_inheritable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.bound_to: tuple[str, int] | None = None
            self.inheritable = False
            self.sockopts: list[tuple[int, int, int]] = []

        def setsockopt(self, level: int, name: int, value: int) -> None:
            self.sockopts.append((level, name, value))

        def bind(self, addr: tuple[str, int]) -> None:
            self.bound_to = addr

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 9001)

        def set_inheritable(self, value: bool) -> None:
            self.inheritable = value

    fake_socket = FakeSocket()
    monkeypatch.setattr(config_module.socket, "socket", lambda family, kind=0: fake_socket)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", host="127.0.0.1", port=0)
    bound_socket = config.bind_socket()
    assert bound_socket is fake_socket
    assert fake_socket.bound_to == ("127.0.0.1", 0)
    assert fake_socket.inheritable is True
    assert fake_socket.sockopts


def test_bind_socket_uses_fromfd_when_fd_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.inheritable = False

        def getsockname(self) -> str:
            return "fd://socket"

        def set_inheritable(self, value: bool) -> None:
            self.inheritable = value

    fake_socket = FakeSocket()
    monkeypatch.setattr(config_module.socket, "fromfd", lambda fd, family, kind: fake_socket)

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", fd=11)
    bound_socket = config.bind_socket()
    assert bound_socket is fake_socket
    assert fake_socket.inheritable is True


def test_bind_socket_uds_sets_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "palfrey.sock"
    chmod_calls: list[tuple[str, int]] = []

    class FakeSocket:
        def __init__(self) -> None:
            self.bound_to: str | None = None
            self.inheritable = False

        def bind(self, path: str) -> None:
            self.bound_to = path

        def set_inheritable(self, value: bool) -> None:
            self.inheritable = value

    fake_socket = FakeSocket()
    monkeypatch.setattr(
        config_module.socket,
        "socket",
        lambda family, kind: fake_socket,
    )
    monkeypatch.setattr(
        config_module.os, "chmod", lambda path, mode: chmod_calls.append((path, mode))
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", uds=str(socket_path))
    bound_socket = config.bind_socket()
    assert bound_socket is fake_socket
    assert fake_socket.bound_to == str(socket_path)
    assert fake_socket.inheritable is True
    assert chmod_calls == [(str(socket_path), 0o666)]


def test_bind_socket_raises_system_exit_on_bind_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def setsockopt(self, *_args) -> None:
            return None

        def bind(self, _addr: tuple[str, int]) -> None:
            raise OSError("boom")

        def set_inheritable(self, _value: bool) -> None:
            return None

    monkeypatch.setattr(
        config_module.socket,
        "socket",
        lambda family, kind=0: FakeSocket(),
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", host="127.0.0.1", port=8000)
    with pytest.raises(SystemExit) as exc_info:
        config.bind_socket()
    assert exc_info.value.code == 1


def test_bind_socket_logs_color_message_extra_for_tcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.inheritable = False

        def setsockopt(self, *_args) -> None:
            return None

        def bind(self, _addr: tuple[str, int]) -> None:
            return None

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 8001)

        def set_inheritable(self, value: bool) -> None:
            self.inheritable = value

    events: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class FakeLogger:
        def info(self, message: str, *args: object, **kwargs: object) -> None:
            events.append((message, args, dict(kwargs)))

        def error(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(config_module.socket, "socket", lambda family, kind=0: FakeSocket())
    monkeypatch.setattr(config_module, "logger", FakeLogger())

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", host="127.0.0.1", port=0)
    config.bind_socket()

    assert events
    message, args, kwargs = events[0]
    assert message == "Palfrey running on %s://%s:%d (Press CTRL+C to quit)"
    assert args == ("http", "127.0.0.1", 8001)
    assert isinstance(kwargs.get("extra"), dict)
    extra = kwargs["extra"]
    assert isinstance(extra, dict)
    assert "color_message" in extra
    assert "Palfrey running on" in str(extra["color_message"])
