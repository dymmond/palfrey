"""Proxy headers middleware.

This middleware updates ASGI scope client/scheme from trusted proxy headers,
following the behavior model used by Uvicorn's ProxyHeadersMiddleware.
"""

from __future__ import annotations

from palfrey.acceleration import split_csv_values
from palfrey.types import ASGIApplication, ReceiveCallable, Scope, SendCallable


class ProxyHeadersMiddleware:
    """Trust and apply ``X-Forwarded-*`` headers for selected client IPs."""

    def __init__(self, app: ASGIApplication, trusted_hosts: str) -> None:
        """Create middleware instance.

        Args:
            app: Wrapped ASGI application.
            trusted_hosts: Comma-separated trusted proxy hosts or ``*``.
        """

        self.app = app
        hosts = split_csv_values(trusted_hosts)
        self.always_trust = "*" in hosts
        self.trusted_hosts = set(hosts)

    def _trusted(self, host: str) -> bool:
        if self.always_trust:
            return True
        return host in self.trusted_hosts

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Apply proxy header transformations and forward the scope."""

        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if not client:
            await self.app(scope, receive, send)
            return

        client_host, client_port = client
        if not self._trusted(str(client_host)):
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {}
        for name, value in scope.get("headers", []):
            headers[name.decode("latin-1").lower()] = value.decode("latin-1")

        forwarded_for = headers.get("x-forwarded-for")
        if forwarded_for:
            parts = [item.strip() for item in forwarded_for.split(",") if item.strip()]
            if parts:
                scope["client"] = (parts[0], int(client_port))

        forwarded_proto = headers.get("x-forwarded-proto")
        if forwarded_proto:
            proto = forwarded_proto.split(",", 1)[0].strip().lower()
            if proto in {"http", "https", "ws", "wss"}:
                scope["scheme"] = proto

        await self.app(scope, receive, send)
