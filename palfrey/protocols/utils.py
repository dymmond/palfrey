from __future__ import annotations

import asyncio
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palfrey.types import Scope


def get_remote_addr(transport: asyncio.Transport) -> tuple[str, int] | None:
    """
    Extract the remote (peer) address from an active asyncio transport.

    This function attempts to retrieve the socket information first to ensure
    the most accurate representation of the remote endpoint. If the socket
    is unavailable, it falls back to the transport's 'peername' extra info.

    Args:
        transport (asyncio.Transport): The active network transport to inspect.

    Returns:
        tuple[str, int] | None: A tuple containing the (host, port) of the remote
            peer, or None if the address cannot be resolved.
    """

    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        try:
            # Attempt to get the peer name directly from the underlying socket
            info = socket_info.getpeername()
            if isinstance(info, tuple) and len(info) >= 2:
                return str(info[0]), int(info[1])
            return None
        except OSError:
            # Handle cases where the socket might have disconnected during inspection
            return None

    # Fallback to standard transport peername if socket object is inaccessible
    info = transport.get_extra_info("peername")
    if isinstance(info, (list, tuple)) and len(info) == 2:
        return str(info[0]), int(info[1])
    return None


def get_local_addr(transport: asyncio.Transport) -> tuple[str, int | None] | None:
    """
    Extract the local (bound) address from an active asyncio transport.

    Resolves the local endpoint information where the server is listening or
    bound. Supports both IPv4/IPv6 address tuples and Unix Domain Socket paths.

    Args:
        transport (asyncio.Transport): The active network transport to inspect.

    Returns:
        tuple[str, int | None] | None: A tuple containing the (host, port). For
            Unix sockets, the port will be None. Returns None if unresolvable.
    """

    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        info = socket_info.getsockname()
        if isinstance(info, tuple) and len(info) >= 2:
            return str(info[0]), int(info[1])
        if isinstance(info, str):
            # Likely a Unix Domain Socket path
            return info, None
        return None

    info = transport.get_extra_info("sockname")
    if isinstance(info, (list, tuple)) and len(info) == 2:
        return str(info[0]), int(info[1])
    if isinstance(info, str):
        return info, None
    return None


def is_ssl(transport: asyncio.Transport) -> bool:
    """
    Determine if the given transport is currently using SSL/TLS encryption.

    Checks the transport's extra information for the presence of an SSL context.

    Args:
        transport (asyncio.Transport): The transport to verify.

    Returns:
        bool: True if the connection is encrypted, False otherwise.
    """

    return bool(transport.get_extra_info("sslcontext"))


def get_client_addr(scope: Scope) -> str:
    """
    Format the client address from an ASGI scope for use in log messages.

    Takes the 'client' tuple (host, port) from the scope and converts it
    into a standardized string representation.

    Args:
        scope (Scope): The ASGI connection scope.

    Returns:
        str: A string formatted as "host:port", or an empty string if
            the client information is missing.
    """

    client = scope.get("client")
    if not client:
        return ""
    return f"{client[0]}:{client[1]}"


def get_path_with_query_string(scope: Scope) -> str:
    """
    Reconstruct the full request path including the query string from the scope.

    The path is percent-encoded to ensure it is valid for log output, and the
    query string is appended if it contains data.

    Args:
        scope (Scope): The ASGI connection scope containing 'path' and
            'query_string'.

    Returns:
        str: The full URL-encoded path, including the '?' and query parameters
            if applicable.
    """

    # Ensure the path is properly escaped for safe logging
    path = urllib.parse.quote(str(scope["path"]))
    query_string = scope.get("query_string", b"")

    if query_string:
        # Query strings in ASGI are bytes, decode to ascii for concatenation
        return f"{path}?{query_string.decode('ascii')}"
    return path
