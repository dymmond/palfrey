from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

# Represents the ASGI connection metadata dictionary.
# This contains information such as the protocol type, client address,
# and headers.
Scope: TypeAlias = dict[str, Any]

# Represents a single ASGI message sent or received over the interface.
# These dictionaries must follow the specific event schemas defined by the
# ASGI specification for HTTP or WebSocket.
Message: TypeAlias = dict[str, Any]

# An asynchronous callable that the application uses to receive events
# from the server's protocol implementation.
ReceiveCallable: TypeAlias = Callable[[], Awaitable[Message]]

# An asynchronous callable that the application uses to send events
# back to the server.
SendCallable: TypeAlias = Callable[[Message], Awaitable[None]]

# The standard ASGI 3.0 single-callable interface for asynchronous
# web applications.
ASGIApplication: TypeAlias = Callable[
    [Scope, ReceiveCallable, SendCallable],
    Awaitable[None],
]

# The instance returned by an ASGI 2.0 application after the scope
# has been initially provided.
ASGI2ApplicationInstance: TypeAlias = Callable[[ReceiveCallable, SendCallable], Awaitable[None]]

# The legacy ASGI 2.0 double-callable interface for asynchronous
# web applications.
ASGI2Application: TypeAlias = Callable[[Scope], ASGI2ApplicationInstance]

# A factory callable that, when invoked with no arguments, returns
# an ASGI application instance.
ASGIApplicationFactory: TypeAlias = Callable[[], ASGIApplication]

# The standard Synchronous WSGI interface (PEP 3333) used for legacy
# application support.
WSGIApplication: TypeAlias = Callable[
    [dict[str, Any], Callable[..., None]],
    list[bytes] | tuple[bytes, ...],
]

# A union type covering all supported application entry points,
# including import strings.
AppType: TypeAlias = (
    ASGIApplication | ASGI2Application | ASGIApplicationFactory | WSGIApplication | str
)

# A collection of raw HTTP headers represented as a list of
# byte-string tuples.
Headers: TypeAlias = list[tuple[bytes, bytes]]

# A network address for a client endpoint, typically consisting
# of a host IP and a port.
ClientAddress: TypeAlias = tuple[str, int]

# A network address for the server endpoint, typically consisting
# of a host IP and a port.
ServerAddress: TypeAlias = tuple[str, int]
