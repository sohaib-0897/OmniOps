"""SSRF-hardened web retrieval with DNS-pinned, bounded HTTP."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from typing import Any, Dict, Iterable, Optional
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpcore
import httpx
import trafilatura
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import AsyncNetworkBackend, AsyncNetworkStream, SOCKET_OPTION

from app.core.config import settings
from app.ingestion.contracts import ExtractionMethod


class URLSecurityError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


_EXPLICIT_BLOCKED_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),   # carrier-grade NAT
    ipaddress.ip_network("198.18.0.0/15"),   # benchmarking networks
    ipaddress.ip_network("169.254.169.254/32"),
)
_BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "metadata.google.internal",
    "metadata", "instance-data.ec2.internal", "instance-data.ec2.internal.",
}


def is_ip_prohibited(ip_str: str) -> bool:
    """Reject loopback, private, link-local, reserved, and non-global targets."""
    try:
        address = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if any(address in network for network in _EXPLICIT_BLOCKED_NETWORKS):
        return True
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        or not address.is_global
    )


def _normalize_hostname(hostname: str) -> str:
    if not hostname or any(ord(char) < 32 or ord(char) == 127 for char in hostname):
        raise URLSecurityError("URL_INVALID", "URL hostname is empty or contains control characters.")
    if "%" in hostname or "/" in hostname or "\\" in hostname:
        raise URLSecurityError("URL_INVALID", "Encoded or ambiguous hostname is not permitted.")
    try:
        normalized = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise URLSecurityError("URL_INVALID", "Hostname is not valid IDNA.") from exc
    if not normalized or normalized in _BLOCKED_HOSTNAMES or normalized.endswith(".localhost"):
        raise URLSecurityError("URL_HOST_BLOCKED", f"Hostname '{hostname}' is restricted.")
    # Reject shortened, decimal, hex, and octal-like numeric spellings rather
    # than relying on platform-specific DNS parsing behavior.
    if normalized.lower().startswith(("0x", "0o")):
        raise URLSecurityError("URL_IP_BLOCKED", "Ambiguous numeric IP notation is not permitted.")
    if all(char.isdigit() or char == "." for char in normalized):
        parts = normalized.split(".")
        if len(parts) != 4 or any(part == "" or (len(part) > 1 and part.startswith("0")) or int(part) > 255 for part in parts):
            raise URLSecurityError("URL_IP_BLOCKED", "Ambiguous numeric IP notation is not permitted.")
    if len(normalized) > 253 or any(len(label) > 63 or not label for label in normalized.split(".")):
        raise URLSecurityError("URL_INVALID", "Hostname is malformed.")
    return normalized


def _port(parsed: SplitResult) -> tuple[int, bool]:
    try:
        port = parsed.port
    except ValueError as exc:
        raise URLSecurityError("URL_PORT_BLOCKED", "Port is malformed or outside the valid range.") from exc
    if port is None:
        return (443 if parsed.scheme.lower() == "https" else 80), False
    return port, True


def _resolve_addresses(hostname: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise URLSecurityError("URL_INVALID", f"DNS resolution failed for host '{hostname}'.") from exc
        addresses = list(dict.fromkeys(item[4][0] for item in info))
    if not addresses:
        raise URLSecurityError("URL_INVALID", f"Host '{hostname}' did not resolve to an address.")
    for address in addresses:
        if is_ip_prohibited(address):
            raise URLSecurityError("URL_IP_BLOCKED", f"Resolved IP '{address}' for host '{hostname}' is restricted.")
    return addresses


def _normalized_url(url: str) -> tuple[str, str, int, list[str]]:
    if not isinstance(url, str) or not url.strip() or any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise URLSecurityError("URL_INVALID", "URL is empty or contains control characters.")
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {item.lower() for item in settings.WEB_ALLOWED_SCHEMES}:
        raise URLSecurityError("URL_SCHEME_BLOCKED", f"Invalid URL scheme '{parsed.scheme}' (URL scheme blocked).")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise URLSecurityError("URL_INVALID", "Embedded URL credentials are not permitted.")
    hostname = _normalize_hostname(parsed.hostname or "")
    port, explicit_port = _port(parsed._replace(scheme=scheme))
    addresses = _resolve_addresses(hostname, port)
    if explicit_port and port not in set(settings.WEB_ALLOWED_PORTS):
        raise URLSecurityError("URL_PORT_BLOCKED", f"Port {port} is not allowed by outbound policy.")
    # Rebuild a canonical URL without a fragment. Preserve IPv6 brackets.
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if explicit_port:
        netloc = f"{netloc}:{port}"
    normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return normalized, hostname, port, addresses


def validate_url_security(url: str) -> str:
    """Validate and canonicalize an outbound URL, resolving every address."""
    return _normalized_url(url)[0]


class _PinnedNetworkBackend(AsyncNetworkBackend):
    """Connect to the address validated for this request while preserving TLS SNI."""

    def __init__(self, pinned_address: str):
        self._pinned_address = pinned_address
        self._backend = AnyIOBackend()

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None, socket_options: Iterable[SOCKET_OPTION] | None = None) -> AsyncNetworkStream:
        return await self._backend.connect_tcp(self._pinned_address, port, timeout=timeout, local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Iterable[SOCKET_OPTION] | None = None) -> AsyncNetworkStream:
        raise OSError("Unix sockets are not permitted by web retrieval policy.")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(self, address: str, verify: ssl.SSLContext | bool = True):
        ssl_context = ssl.create_default_context() if verify is True else verify
        self._pool = httpcore.AsyncConnectionPool(ssl_context=ssl_context, max_connections=4, max_keepalive_connections=0, network_backend=_PinnedNetworkBackend(address))

    async def __aenter__(self):
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._pool.__aexit__(exc_type, exc_value, traceback)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        req = httpcore.Request(method=request.method, url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path), headers=request.headers.raw, content=request.stream, extensions=request.extensions)
        response = await self._pool.handle_async_request(req)
        return httpx.Response(status_code=response.status, headers=response.headers, stream=httpx._transports.default.AsyncResponseStream(response.stream), extensions=response.extensions, request=request)

    async def aclose(self) -> None:
        await self._pool.aclose()


async def fetch_web_page_content(url: str, max_size_bytes: int = settings.WEB_MAX_RESPONSE_BYTES) -> Dict[str, Any]:
    """Fetch HTML/text with pinned DNS, redirect revalidation, and byte caps."""
    current_url, _, _, addresses = _normalized_url(url)
    redirects = 0
    timeout = httpx.Timeout(settings.WEB_READ_TIMEOUT_SECONDS, connect=settings.WEB_CONNECT_TIMEOUT_SECONDS)
    try:
        async with asyncio.timeout(settings.WEB_TOTAL_TIMEOUT_SECONDS):
            while True:
                transport = _PinnedHTTPTransport(addresses[0], verify=True)
                async with httpx.AsyncClient(transport=transport, timeout=timeout, follow_redirects=False, trust_env=False, headers={"User-Agent": "OmniOps-Security-Agent/1.0"}) as client:
                    async with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise URLSecurityError("URL_REDIRECT_BLOCKED", "Redirect response has no Location header.")
                            if redirects >= settings.WEB_MAX_REDIRECTS:
                                raise URLSecurityError("URL_REDIRECT_BLOCKED", "Maximum redirect count exceeded.")
                            current_url, _, _, addresses = _normalized_url(urljoin(current_url, location))
                            redirects += 1
                            continue
                        if response.status_code != 200:
                            raise URLSecurityError("URL_FETCH_FAILED", f"HTTP request returned status {response.status_code}.")
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if not content_type or content_type not in {item.lower() for item in settings.WEB_ALLOWED_CONTENT_TYPES}:
                            raise URLSecurityError("URL_CONTENT_TYPE_BLOCKED", f"Content type '{content_type}' is not allowed.")
                        content_length = response.headers.get("content-length")
                        if content_length and content_length.isdigit() and int(content_length) > max_size_bytes:
                            raise URLSecurityError("URL_RESPONSE_TOO_LARGE", "Response exceeds the configured byte limit.")
                        chunks: list[bytes] = []
                        received = 0
                        async for chunk in response.aiter_bytes():
                            received += len(chunk)
                            if received > max_size_bytes or received > settings.WEB_MAX_DECODED_BYTES:
                                raise URLSecurityError("URL_RESPONSE_TOO_LARGE", "Decoded response exceeds the configured byte limit.")
                            chunks.append(chunk)
                        body = b"".join(chunks)
                html_text = body.decode("utf-8", "replace")
                metadata = trafilatura.metadata.extract_metadata(html_text)
                extracted_text = trafilatura.extract(html_text, include_tables=True, include_links=False)
                return {
                    "url": current_url,
                    "title": metadata.title if metadata else "Web Page",
                    "content": extracted_text or "",
                    "extraction_status": "EXTRACTED" if extracted_text else "TEXT_EXTRACTION_UNAVAILABLE",
                    "extraction_method": ExtractionMethod.WEB_EXTRACTION.value,
                    "status_code": 200,
                    "content_trusted": False,
                    "content_label": "UNTRUSTED_WEB_DATA",
                }
    except asyncio.TimeoutError as exc:
        raise URLSecurityError("URL_TIMEOUT", "Web retrieval exceeded the configured timeout.") from exc


class SafeWebRetriever:
    """Authoritative web retrieval capability used by production callers."""

    async def fetch(self, url: str) -> Dict[str, Any]:
        return await fetch_web_page_content(url)
