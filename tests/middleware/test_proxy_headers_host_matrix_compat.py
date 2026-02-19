from __future__ import annotations

import pytest

from palfrey.middleware.proxy_headers import _TrustedHosts

_TRUSTED_NOTHING: list[str] = []
_TRUSTED_EVERYTHING = "*"
_TRUSTED_IPV4_ADDRS = "127.0.0.1,10.0.0.1"
_TRUSTED_IPV4_NETS = ["127.0.0.0/8", "10.0.0.0/8"]
_TRUSTED_IPV6_ADDRS = [
    "2001:db8::",
    "2001:0db8:0001:0000:0000:0ab9:C0A8:0102",
]
_TRUSTED_IPV6_NETS = "2001:db8:abcd:0012::0/64"
_TRUSTED_LITERALS = "unix:///tmp/app.sock,/tmp/app.sock,service-proxy"


@pytest.mark.parametrize(
    ("trusted_hosts", "host", "expected"),
    [
        (_TRUSTED_NOTHING, "127.0.0.1", False),
        (_TRUSTED_NOTHING, "10.1.1.1", False),
        (_TRUSTED_NOTHING, "2001:db8::", False),
        (_TRUSTED_NOTHING, "service-proxy", False),
        (_TRUSTED_NOTHING, "", False),
        (_TRUSTED_EVERYTHING, "127.0.0.1", True),
        (_TRUSTED_EVERYTHING, "10.1.1.1", True),
        (_TRUSTED_EVERYTHING, "2001:db8::", True),
        (_TRUSTED_EVERYTHING, "service-proxy", True),
        (_TRUSTED_EVERYTHING, "", True),
        (_TRUSTED_IPV4_ADDRS, "127.0.0.1", True),
        (_TRUSTED_IPV4_ADDRS, "10.0.0.1", True),
        (_TRUSTED_IPV4_ADDRS, "10.1.1.1", False),
        (_TRUSTED_IPV4_ADDRS, "2001:db8::", False),
        (_TRUSTED_IPV4_ADDRS, "service-proxy", False),
        (_TRUSTED_IPV4_NETS, "127.0.0.1", True),
        (_TRUSTED_IPV4_NETS, "127.255.255.255", True),
        (_TRUSTED_IPV4_NETS, "10.10.10.10", True),
        (_TRUSTED_IPV4_NETS, "192.168.0.1", False),
        (_TRUSTED_IPV4_NETS, "2001:db8::", False),
        (_TRUSTED_IPV6_ADDRS, "2001:db8::", True),
        (_TRUSTED_IPV6_ADDRS, "2001:db8:abcd:0012::1", False),
        (_TRUSTED_IPV6_ADDRS, "::1", False),
        (_TRUSTED_IPV6_ADDRS, "127.0.0.1", False),
        (_TRUSTED_IPV6_NETS, "2001:db8:abcd:0012::1", True),
        (_TRUSTED_IPV6_NETS, "2001:db8:abcd:0012:ffff::1", True),
        (_TRUSTED_IPV6_NETS, "2001:db8::", False),
        (_TRUSTED_IPV6_NETS, "127.0.0.1", False),
        (_TRUSTED_LITERALS, "unix:///tmp/app.sock", True),
        (_TRUSTED_LITERALS, "/tmp/app.sock", True),
        (_TRUSTED_LITERALS, "service-proxy", True),
        (_TRUSTED_LITERALS, "another-proxy", False),
    ],
)
def test_trusted_hosts_membership_matrix(
    trusted_hosts: list[str] | str,
    host: str,
    expected: bool,
) -> None:
    assert (host in _TrustedHosts(trusted_hosts)) is expected


@pytest.mark.parametrize(
    ("trusted_hosts", "forwarded_for", "expected"),
    [
        ("*", "198.51.100.10, 10.0.0.1", "198.51.100.10"),
        ("10.0.0.1", "198.51.100.10, 10.0.0.1", "198.51.100.10"),
        ("10.0.0.1,10.0.0.2", "198.51.100.10, 10.0.0.1, 10.0.0.2", "198.51.100.10"),
        ("10.0.0.1", "198.51.100.10, 198.51.100.11", "198.51.100.11"),
        ("10.0.0.1", "10.0.0.1", "10.0.0.1"),
    ],
)
def test_trusted_hosts_extracts_effective_client(
    trusted_hosts: str,
    forwarded_for: str,
    expected: str,
) -> None:
    assert _TrustedHosts(trusted_hosts).get_trusted_client_host(forwarded_for) == expected
