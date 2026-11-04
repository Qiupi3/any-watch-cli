from __future__ import annotations

"""DNS-over-HTTPS helpers for sites whose A records are missing locally.

Some ISPs hand out resolvers that silently drop records for streaming sites.
When a normal request fails we resolve the hostname through Cloudflare/Google
DoH and retry against the returned address, keeping the original ``Host``
header and TLS SNI intact.
"""

from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

_DOH_ENDPOINTS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)

# Successful lookups live for the lifetime of the process.
_DNS_CACHE: dict[str, str] = {}


async def resolve_ipv4(host: str, timeout: float = 6.0) -> Optional[str]:
    """Resolve ``host`` to an IPv4 address through public DoH resolvers."""
    host = host.lower().rstrip(".")
    cached = _DNS_CACHE.get(host)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for endpoint in _DOH_ENDPOINTS:
            try:
                response = await client.get(
                    endpoint,
                    params={"name": host, "type": "A"},
                    headers={"Accept": "application/dns-json"},
                )
                payload = response.json()
            except Exception:
                continue

            answers = payload.get("Answer") if isinstance(payload, dict) else None
            for answer in answers or []:
                if not isinstance(answer, dict):
                    continue
                if answer.get("type") == 1 and answer.get("data"):
                    address = str(answer["data"])
                    _DNS_CACHE[host] = address
                    return address
    return None


async def get_with_doh(
    client: httpx.AsyncClient,
    url: str,
    **kwargs,
) -> Optional[httpx.Response]:
    """GET ``url``, falling back to a DoH-resolved address on transport errors."""
    response: Optional[httpx.Response] = None
    try:
        response = await client.get(url, **kwargs)
        if response.status_code < 500:
            return response
    except Exception:
        response = None

    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return response

    address = await resolve_ipv4(host)
    if not address:
        return response

    netloc = address if parts.port is None else f"{address}:{parts.port}"
    address_url = urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    )

    headers = dict(kwargs.pop("headers", None) or {})
    headers["Host"] = host
    extensions = dict(kwargs.pop("extensions", None) or {})
    extensions["sni_hostname"] = host

    try:
        return await client.get(
            address_url, headers=headers, extensions=extensions, **kwargs
        )
    except Exception:
        return response
