"""Strict parsing for local-only AI HTTP endpoints.

SciPlotter's privacy contract permits local model runtimes only.  This module
intentionally validates literal hosts without DNS resolution so a configured
endpoint cannot silently become a LAN or cloud service.
"""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
import urllib.request
from urllib.parse import urlsplit


DEFAULT_LOCAL_AI_BASE_URL = "http://127.0.0.1:11434"


class LocalEndpointError(ValueError):
    """Raised when an AI base URL is not a safe loopback HTTP endpoint."""


class _RejectLocalRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward a local inference request to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalEndpointError("Local AI endpoints may not redirect requests.")


@dataclass(frozen=True)
class LocalHttpEndpoint:
    """Parsed and canonicalized local HTTP(S) endpoint."""

    scheme: str
    host: str
    port: int | None = None
    path: str = ""

    @property
    def url(self) -> str:
        rendered_host = f"[{self.host}]" if ":" in self.host else self.host
        port = f":{self.port}" if self.port is not None else ""
        return f"{self.scheme}://{rendered_host}{port}{self.path}"


def parse_local_http_base_url(value: str) -> LocalHttpEndpoint:
    """Parse *value* and reject anything outside the local loopback host.

    Allowed hosts are the literal name ``localhost``, any IPv4 address in
    ``127.0.0.0/8``, and the IPv6 loopback address ``::1``.  Credentials,
    queries and fragments are not valid parts of an AI API base URL.
    """

    if not isinstance(value, str) or not value.strip():
        raise LocalEndpointError("Local AI base URL is empty.")
    text = value.strip()
    if any(character.isspace() or ord(character) == 127 for character in text):
        raise LocalEndpointError("Local AI base URL contains whitespace or control characters.")

    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise LocalEndpointError("Local AI base URL is malformed.") from exc

    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise LocalEndpointError("Local AI base URL must use HTTP or HTTPS.")
    if not parsed.netloc or not hostname:
        raise LocalEndpointError("Local AI base URL must include a host.")
    if parsed.username is not None or parsed.password is not None:
        raise LocalEndpointError("Credentials are not allowed in a local AI base URL.")
    if parsed.query or parsed.fragment:
        raise LocalEndpointError("Query strings and fragments are not allowed in an AI base URL.")
    if port is not None and not 1 <= port <= 65535:
        raise LocalEndpointError("Local AI base URL has an invalid port.")

    host = hostname.casefold()
    if "%" in host:
        # IPv6 zone identifiers are unnecessary for ::1 and make URL identity
        # harder to audit consistently across platforms.
        raise LocalEndpointError("IPv6 zone identifiers are not allowed.")
    if host == "localhost":
        canonical_host = host
    else:
        try:
            address = ip_address(host)
        except ValueError as exc:
            raise LocalEndpointError("Local AI base URL must use a literal loopback host.") from exc
        allowed_ipv4 = isinstance(address, IPv4Address) and address.packed[0] == 127
        allowed_ipv6 = isinstance(address, IPv6Address) and address == IPv6Address("::1")
        if not (allowed_ipv4 or allowed_ipv6):
            raise LocalEndpointError("Local AI base URL must use a loopback address.")
        canonical_host = address.compressed

    path = parsed.path.rstrip("/")
    if "\\" in path:
        raise LocalEndpointError("Backslashes are not allowed in an AI base URL.")
    return LocalHttpEndpoint(
        scheme=scheme,
        host=canonical_host,
        port=port,
        path=path,
    )


def normalize_local_http_base_url(value: str) -> str:
    """Return the canonical URL for a validated local AI endpoint."""

    return parse_local_http_base_url(value).url


def local_http_urlopen(
    request: str | urllib.request.Request,
    *,
    timeout: float,
):
    """Open a loopback request without consulting system proxy settings.

    ``urllib.request.urlopen`` honors environment and operating-system proxy
    configuration.  Some proxies do not exempt loopback hosts, which could
    leak a research prompt even when the target URL is ``127.0.0.1``.  Build a
    dedicated opener with an empty proxy map and a no-redirect policy for every
    local inference request. Model/runtime downloads deliberately do not use
    this function and may follow the customer's normal proxy policy.
    """

    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    parse_local_http_base_url(url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectLocalRedirects(),
    )
    return opener.open(request, timeout=max(0.05, float(timeout)))
