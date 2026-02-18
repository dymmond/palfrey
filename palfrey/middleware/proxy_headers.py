"""Proxy headers middleware.

This middleware updates ASGI scope client/scheme from trusted proxy headers,
following Uvicorn's documented semantics.
"""

from __future__ import annotations

import ipaddress

from palfrey.acceleration import split_csv_values
from palfrey.types import ASGIApplication, ReceiveCallable, Scope, SendCallable


class ProxyHeadersMiddleware:
    """Trust and apply ``X-Forwarded-*`` headers for selected client IPs."""

    def __init__(self, app: ASGIApplication, trusted_hosts: list[str] | str) -> None:
        """Create middleware instance.

        Args:
            app: Wrapped ASGI application.
            trusted_hosts: Trusted host configuration. Accepts comma-separated
                hosts, IP/CIDR entries, literals, or ``*``.
        """

        self.app = app
        self.trusted_hosts = _TrustedHosts(trusted_hosts)

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """Apply proxy header transformations and forward the scope."""

        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else None
        if client_host not in self.trusted_hosts:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        forwarded_proto_raw = headers.get(b"x-forwarded-proto")
        if forwarded_proto_raw is not None:
            forwarded_proto = forwarded_proto_raw.decode("latin1").strip()
            if forwarded_proto in {"http", "https", "ws", "wss"}:
                if scope["type"] == "websocket":
                    scope["scheme"] = forwarded_proto.replace("http", "ws")
                else:
                    scope["scheme"] = forwarded_proto

        forwarded_for_raw = headers.get(b"x-forwarded-for")
        if forwarded_for_raw is not None:
            forwarded_for = forwarded_for_raw.decode("latin1")
            host = self.trusted_hosts.get_trusted_client_host(forwarded_for)
            if host:
                scope["client"] = (host, 0)

        await self.app(scope, receive, send)


class _TrustedHosts:
    """Represent trusted host configuration for proxy middleware decisions."""

    def __init__(self, trusted_hosts: list[str] | str) -> None:
        """Parse trusted host definitions into lookup structures.

        Args:
            trusted_hosts: Trusted host values.
        """

        self.always_trust = trusted_hosts in ("*", ["*"])
        self.trusted_literals: set[str] = set()
        self.trusted_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        self.trusted_networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()

        if self.always_trust:
            return

        values = (
            split_csv_values(trusted_hosts) if isinstance(trusted_hosts, str) else trusted_hosts
        )
        for raw_value in values:
            value = raw_value.strip()
            if not value:
                continue

            if "/" in value:
                try:
                    self.trusted_networks.add(ipaddress.ip_network(value))
                except ValueError:
                    self.trusted_literals.add(value)
                continue

            try:
                self.trusted_ips.add(ipaddress.ip_address(value))
            except ValueError:
                self.trusted_literals.add(value)

    def __contains__(self, host: str | None) -> bool:
        """Return whether host should be treated as trusted."""

        if self.always_trust:
            return True
        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return host in self.trusted_literals

        if ip in self.trusted_ips:
            return True
        return any(ip in network for network in self.trusted_networks)

    def get_trusted_client_host(self, forwarded_for: str) -> str:
        """Extract effective client host from ``X-Forwarded-For`` value.

        Args:
            forwarded_for: Raw ``X-Forwarded-For`` header value.

        Returns:
            First untrusted host when scanning from right-to-left, or leftmost
            host when all entries are trusted.
        """

        hosts = split_csv_values(forwarded_for)
        if not hosts:
            return ""

        if self.always_trust:
            return hosts[0]

        for host in reversed(hosts):
            if host not in self:
                return host
        return hosts[0]
