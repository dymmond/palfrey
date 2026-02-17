"""Shared type aliases for Palfrey internals.

The aliases in this module define the ASGI callable contracts used across the
runtime, protocol implementations, and test fixtures.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

Scope: TypeAlias = dict[str, Any]
Message: TypeAlias = dict[str, Any]
ReceiveCallable: TypeAlias = Callable[[], Awaitable[Message]]
SendCallable: TypeAlias = Callable[[Message], Awaitable[None]]
ASGIApplication: TypeAlias = Callable[[Scope, ReceiveCallable, SendCallable], Awaitable[None]]
ASGI2ApplicationInstance: TypeAlias = Callable[[ReceiveCallable, SendCallable], Awaitable[None]]
ASGI2Application: TypeAlias = Callable[[Scope], ASGI2ApplicationInstance]
ASGIApplicationFactory: TypeAlias = Callable[[], ASGIApplication]
WSGIApplication: TypeAlias = Callable[[dict[str, Any], Callable[..., None]], list[bytes] | tuple[bytes, ...]]
AppType: TypeAlias = ASGIApplication | ASGI2Application | ASGIApplicationFactory | WSGIApplication | str
Headers: TypeAlias = list[tuple[bytes, bytes]]
ClientAddress: TypeAlias = tuple[str, int]
ServerAddress: TypeAlias = tuple[str, int]
