"""Protocol-level utility helpers.

This module mirrors Uvicorn's transport/scope helper shapes for parity in
address extraction and request logging helpers.
"""

from __future__ import annotations

import asyncio
import urllib.parse

from palfrey.types import Scope


def get_remote_addr(transport: asyncio.Transport) -> tuple[str, int] | None:
    """Resolve remote address from a transport."""

    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        try:
            info = socket_info.getpeername()
            if isinstance(info, tuple) and len(info) >= 2:
                return str(info[0]), int(info[1])
            return None
        except OSError:  # pragma: no cove - inconsistent across loop implementations.
            return None

    info = transport.get_extra_info("peername")
    if isinstance(info, (list, tuple)) and len(info) == 2:
        return str(info[0]), int(info[1])
    return None


def get_local_addr(transport: asyncio.Transport) -> tuple[str, int | None] | None:
    """Resolve local/bound address from a transport."""

    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        info = socket_info.getsockname()
        if isinstance(info, tuple) and len(info) >= 2:
            return str(info[0]), int(info[1])
        if isinstance(info, str):
            return info, None
        return None

    info = transport.get_extra_info("sockname")
    if isinstance(info, (list, tuple)) and len(info) == 2:  # pragma: no cover
        return str(info[0]), int(info[1])
    if isinstance(info, str):
        return info, None
    return None


def is_ssl(transport: asyncio.Transport) -> bool:
    """Return whether transport carries SSL context metadata."""

    return bool(transport.get_extra_info("sslcontext"))


def get_client_addr(scope: Scope) -> str:
    """Format ``scope['client']`` as ``host:port`` for log records."""

    client = scope.get("client")
    if not client:
        return ""
    return f"{client[0]}:{client[1]}"


def get_path_with_query_string(scope: Scope) -> str:
    """Return escaped request path with query string suffix when present."""

    path = urllib.parse.quote(str(scope["path"]))
    query_string = scope.get("query_string", b"")
    if query_string:
        return f"{path}?{query_string.decode('ascii')}"
    return path
