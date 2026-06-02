"""Shared HTTP session utilities.

Provides a curl_cffi session that impersonates Chrome browser to bypass
TLS fingerprinting blocks. Falls back to requests.Session if curl_cffi
is not installed.

Includes SSRF protection: blocks requests to internal/private IP ranges.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests


# RFC 1918 + link-local + loopback + broadcast ranges
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private Class A
    ipaddress.ip_network("172.16.0.0/12"),     # private Class B
    ipaddress.ip_network("192.168.0.0/16"),    # private Class C
    ipaddress.ip_network("169.254.0.0/16"),    # link-local
    ipaddress.ip_network("0.0.0.0/8"),         # current network
    ipaddress.ip_network("100.64.0.0/10"),     # carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),      # IETF protocol assignments
    ipaddress.ip_network("198.18.0.0/15"),     # benchmarking
    ipaddress.ip_network("224.0.0.0/4"),       # multicast
    ipaddress.ip_network("240.0.0.0/4"),       # reserved
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


class SSRFError(Exception):
    """Raised when a request targets an internal/blocked address."""
    pass


def validate_url(url: str) -> str:
    """Validate that a URL does not target an internal/private network.

    Args:
        url: The URL to validate.

    Returns:
        The original URL if validation passes.

    Raises:
        SSRFError: If the URL targets a blocked network range.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise SSRFError(f"Invalid URL: no hostname in '{url}'")

    # Allow localhost only for LM Studio (127.0.0.1:1234 / 192.168.56.1:1234)
    # All other internal IPs are blocked
    llm_url = _get_llm_base_url()
    if llm_url:
        llm_parsed = urlparse(llm_url)
        if hostname == llm_parsed.hostname:
            return url

    # Resolve hostname to IP and check against blocked ranges
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    raise SSRFError(
                        f"SSRF blocked: '{hostname}' resolves to {ip} "
                        f"(in {network}). Requests to internal networks are not allowed."
                    )
    except socket.gaierror:
        # DNS resolution failed — let the request proceed and fail naturally
        # (Don't block on DNS failure as it may be transient)
        pass

    return url


def _get_llm_base_url() -> str | None:
    """Get the configured LLM base URL from environment."""
    import os
    return os.environ.get("BREACHALPHA_LLM_URL")


def get_browser_session():
    """Get a curl_cffi session that impersonates Chrome browser.

    Returns:
        Tuple of (session, is_curl_cffi) where is_curl_cffi indicates
        whether the session uses curl_cffi (True) or plain requests (False).
    """
    try:
        from curl_cffi import requests as curl_requests
        session = curl_requests.Session(impersonate="chrome")
        return session, True
    except ImportError:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        })
        return session, False
