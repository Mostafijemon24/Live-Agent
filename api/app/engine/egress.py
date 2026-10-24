"""Application-level egress control for every outbound HTTP request the engine makes.

- Only hosts on an explicit allowlist (workspace allowed domains, or the operator-configured
  model endpoint). A domain entry also allows its subdomains.
- DNS is resolved here and every resolved address must be public (no loopback, private,
  link-local, multicast, reserved or cloud-metadata addresses) unless private networks are
  explicitly allowed (development, or an operator-configured local model server).
- The connection is pinned to the checked IP address (TLS still verifies the hostname via
  SNI), so a second DNS answer cannot redirect the request (DNS rebinding).
- Redirects are followed manually, only to the same host, at most `egress_max_redirects`.
- Response bodies are capped at `egress_max_bytes`; requests time out.
- Environment proxy variables are ignored; only EGRESS_PROXY_URL is used.

This reduces SSRF and exfiltration risk inside the application. It does not replace a network
level egress firewall, which deploy/ documents for production.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import Settings, get_settings


class EgressBlocked(Exception):
    """The request was refused by policy before anything was sent."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EgressFailed(Exception):
    """The request was allowed but failed (network error, timeout)."""

    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class EgressPolicy:
    allowed_hosts: frozenset[str]
    allow_private: bool = False
    allow_http: bool = False
    allowed_ports: frozenset[int] = field(default_factory=lambda: frozenset({80, 443}))


@dataclass(frozen=True)
class EgressResponse:
    status: int
    url: str
    headers: dict[str, str]
    body: bytes
    truncated: bool
    elapsed_ms: int

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def normalize_host(host: str) -> str:
    h = host.strip().rstrip(".").lower()
    try:
        return h.encode("idna").decode("ascii")
    except UnicodeError:
        return h


def host_allowed(host: str, allowed: Iterable[str]) -> bool:
    h = normalize_host(host)
    for entry in allowed:
        e = normalize_host(entry)
        if e and (h == e or h.endswith("." + e)):
            return True
    return False


_EXTRA_BLOCKED = (ipaddress.ip_network("fec0::/10"),)  # deprecated site-local IPv6


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_public(ip.ipv4_mapped)
    if any(ip in n for n in _EXTRA_BLOCKED):
        return False
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_private
        and not ip.is_unspecified
    )


def check_url(url: str, policy: EgressPolicy) -> tuple[str, str, int, str]:
    """Validate a URL against the policy. Returns (scheme, host, port, path_with_query)."""
    if len(url) > 2048:
        raise EgressBlocked("url_too_long", "The address is too long.")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http"):
        raise EgressBlocked("scheme_not_allowed", "Only https:// addresses can be opened.")
    if scheme == "http" and not policy.allow_http:
        raise EgressBlocked("scheme_not_allowed", "Only https:// addresses can be opened.")
    if parts.username or parts.password:
        raise EgressBlocked("credentials_in_url", "Addresses with embedded credentials are not allowed.")
    if not parts.hostname:
        raise EgressBlocked("invalid_url", "That address has no host name.")
    host = normalize_host(parts.hostname)
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise EgressBlocked("invalid_url", "That address has an invalid port.") from None
    if port not in policy.allowed_ports:
        raise EgressBlocked("port_not_allowed", f"Port {port} is not allowed.")
    if not host_allowed(host, policy.allowed_hosts):
        raise EgressBlocked("domain_not_allowed", f"{host} is not on this workspace's allowed domains list.")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return scheme, host, port, path


def resolve_checked(host: str, port: int, policy: EgressPolicy) -> str:
    """Resolve and check every address. Returns the IP to connect to."""
    try:
        literal = ipaddress.ip_address(host)
        addrs = [literal]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise EgressFailed("dns_failed", f"Could not resolve {host}.", retryable=True) from None
        addrs = [ipaddress.ip_address(str(i[4][0]).split("%")[0]) for i in infos]
    if not addrs:
        raise EgressFailed("dns_failed", f"Could not resolve {host}.")
    if not policy.allow_private:
        for a in addrs:
            if not _ip_is_public(a):
                raise EgressBlocked(
                    "private_address", f"{host} resolves to a private or internal address, which is not allowed."
                )
    return str(addrs[0])


class EgressClient:
    def __init__(self, policy: EgressPolicy, settings: Settings | None = None) -> None:
        self.policy = policy
        self.settings = settings or get_settings()

    def _send(self, method: str, url: str, headers: dict[str, str], content: bytes | None, timeout: float) -> Any:
        scheme, host, port, path = check_url(url, self.policy)
        ip = resolve_checked(host, port, self.policy)
        hdrs = {"User-Agent": self.settings.egress_user_agent, **headers}
        extensions: dict[str, Any] = {}
        if self.settings.egress_proxy_url:
            target = url  # the forward proxy connects; addresses were still checked above
            proxy: str | None = self.settings.egress_proxy_url
        else:
            netloc_ip = f"[{ip}]" if ":" in ip else ip
            default_port = 443 if scheme == "https" else 80
            netloc = netloc_ip if port == default_port else f"{netloc_ip}:{port}"
            target = urlunsplit((scheme, netloc, path, "", ""))
            hdrs["Host"] = host if port == default_port else f"{host}:{port}"
            if scheme == "https":
                extensions["sni_hostname"] = host
            proxy = None
        client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, proxy=proxy)
        req = client.build_request(method, target, headers=hdrs, content=content, extensions=extensions)
        return client, req, host

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> EgressResponse:
        timeout = timeout or self.settings.egress_timeout_seconds
        cap = max_bytes or self.settings.egress_max_bytes
        started = time.monotonic()
        deadline = started + 2 * timeout  # overall cap: a slow-drip response can't keep a worker busy
        current = url
        first_host = normalize_host(urlsplit(url).hostname or "")
        for _hop in range(self.settings.egress_max_redirects + 1):
            client, req, host = self._send(method, current, headers or {}, content, timeout)
            if host != first_host:
                client.close()
                raise EgressBlocked("cross_host_redirect", "The site redirected to a different host, which is blocked.")
            try:
                with client:
                    resp = client.send(req, stream=True)
                    try:
                        if resp.is_redirect and method == "GET":
                            loc = resp.headers.get("location", "")
                            current = urljoin(current, loc)
                            continue
                        body = bytearray()
                        truncated = False
                        for chunk in resp.iter_bytes():
                            if time.monotonic() > deadline:
                                raise EgressFailed("timeout", f"{host} sent its response too slowly.")
                            body.extend(chunk)
                            if len(body) > cap:
                                del body[cap:]
                                truncated = True
                                break
                        return EgressResponse(
                            status=resp.status_code,
                            url=current,
                            headers={k.lower(): v for k, v in resp.headers.items()},
                            body=bytes(body),
                            truncated=truncated,
                            elapsed_ms=int((time.monotonic() - started) * 1000),
                        )
                    finally:
                        resp.close()
            except httpx.TimeoutException:
                raise EgressFailed("timeout", f"{host} did not respond in time.") from None
            except httpx.HTTPError as e:
                raise EgressFailed("network_error", f"Could not connect to {host} ({type(e).__name__}).") from None
        raise EgressBlocked("too_many_redirects", "Too many redirects.")

    def get(self, url: str, **kw: Any) -> EgressResponse:
        return self.request("GET", url, **kw)


def workspace_policy(allowed_domains: Iterable[str], settings: Settings | None = None) -> EgressPolicy:
    s = settings or get_settings()
    return EgressPolicy(
        allowed_hosts=frozenset(normalize_host(d) for d in allowed_domains),
        allow_private=s.egress_allow_private_networks,
        allow_http=s.egress_allow_http,
        allowed_ports=frozenset({80, 443}) if not s.egress_allow_private_networks else frozenset(range(1, 65536)),
    )
