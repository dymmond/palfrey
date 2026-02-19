from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

from palfrey.acceleration import split_csv_values

if TYPE_CHECKING:
    from palfrey.types import ASGIApplication, ReceiveCallable, Scope, SendCallable


class ProxyHeadersMiddleware:
    """
    Middleware that updates the ASGI scope based on 'X-Forwarded-For' and 'X-Forwarded-Proto'.

    When an application is behind a proxy, the direct connection comes from the proxy's IP.
    This middleware inspects the headers provided by the proxy to restore the original
    client IP and the original connection scheme (HTTP vs HTTPS).

    Attributes:
        app (ASGIApplication): The next ASGI application in the stack.
        trusted_hosts (_TrustedHosts): A container for IP/Network verification logic.
    """

    def __init__(self, app: ASGIApplication, trusted_hosts: list[str] | str) -> None:
        """
        Initialize the middleware with a set of trusted proxies.

        Args:
            app (ASGIApplication): The wrapped ASGI application.
            trusted_hosts (list[str] | str): A list or comma-separated string of IPs,
                CIDR networks, or "*" to trust all proxies.
        """
        self.app = app
        self.trusted_hosts = _TrustedHosts(trusted_hosts)

    async def __call__(self, scope: Scope, receive: ReceiveCallable, send: SendCallable) -> None:
        """
        Process the ASGI scope to apply proxy header transformations.

        This method ignores 'lifespan' events and only applies changes if the direct
        connecting client IP is found within the configured 'trusted_hosts'.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (ReceiveCallable): The async callable to receive messages.
            send (SendCallable): The async callable to send messages.
        """
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        # Determine if the immediate peer is a trusted proxy
        client = scope.get("client")
        client_host = client[0] if client else None

        if client_host not in self.trusted_hosts:
            await self.app(scope, receive, send)
            return

        # Prepare headers for lookup; using a dict for O(1) access to byte keys
        headers = dict(scope.get("headers", []))

        # Handle Protocol Scheme (http vs https / ws vs wss)
        forwarded_proto_raw = headers.get(b"x-forwarded-proto")
        if forwarded_proto_raw is not None:
            forwarded_proto = forwarded_proto_raw.decode("latin1").strip().lower()
            if forwarded_proto in {"http", "https", "ws", "wss"}:
                if scope["type"] == "websocket":
                    # Ensure websocket scopes use websocket schemes
                    scope["scheme"] = forwarded_proto.replace("http", "ws")
                else:
                    scope["scheme"] = forwarded_proto

        # Handle Client IP Address
        forwarded_for_raw = headers.get(b"x-forwarded-for")
        if forwarded_for_raw is not None:
            forwarded_for = forwarded_for_raw.decode("latin1")
            host = self.trusted_hosts.get_trusted_client_host(forwarded_for)
            if host:
                # Port is set to 0 as it is usually not provided by proxies
                scope["client"] = (host, 0)

        await self.app(scope, receive, send)


class _TrustedHosts:
    """
    Internal utility to manage and validate IP addresses against trusted configurations.

    This class parses various input formats (individual IPs, CIDR ranges, and wildcards)
    into structured ipaddress objects for high-performance membership testing.
    """

    def __init__(self, trusted_hosts: list[str] | str) -> None:
        """
        Parse trusted host definitions into lookup structures.

        Args:
            trusted_hosts (list[str] | str): Trusted host values to be parsed.
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

            # Check if the entry is a CIDR network range
            if "/" in value:
                try:
                    self.trusted_networks.add(ipaddress.ip_network(value))
                except ValueError:
                    self.trusted_literals.add(value)
                continue

            # Attempt to parse as a single IP address
            try:
                self.trusted_ips.add(ipaddress.ip_address(value))
            except ValueError:
                # Fallback to string literal if not a valid IP
                self.trusted_literals.add(value)

    def __contains__(self, host: str | None) -> bool:
        """
        Determine if a specific host string is within the trusted definitions.

        Args:
            host (str | None): The host IP or name to check.

        Returns:
            bool: True if the host is trusted.
        """
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

        # Check if the IP falls within any trusted CIDR networks
        return any(ip in network for network in self.trusted_networks)

    def get_trusted_client_host(self, forwarded_for: str) -> str:
        """
        Extract the actual client host from an 'X-Forwarded-For' chain.

        The chain is parsed from right to left. The first host that is NOT a
        trusted proxy is considered the actual client.

        Args:
            forwarded_for (str): The raw, comma-separated 'X-Forwarded-For' header value.

        Returns:
            str: The resolved client host IP address.
        """
        hosts = split_csv_values(forwarded_for)
        if not hosts:
            return ""

        if self.always_trust:
            # If all proxies are trusted, the leftmost host is the client
            return hosts[0]

        # Scan right-to-left to find the first untrusted IP
        for host in reversed(hosts):
            if host not in self:
                return host

        # If all hosts in the chain are trusted, return the leftmost one
        return hosts[0]
