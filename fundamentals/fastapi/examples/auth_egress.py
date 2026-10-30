"""HTTPS allowlist with DNS validation at the actual connection boundary.

Baseline: httpcore 1.0.9. Uses normal certificate validation and original-host SNI.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpcore


class BlockedDestination(ValueError):
    pass


def validate_url(url, allowed_hosts):
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise BlockedDestination("invalid URL") from error
    if (parts.scheme != "https" or parts.hostname not in allowed_hosts
            or parts.username is not None or parts.password is not None
            or port not in (None, 443) or parts.fragment):
        raise BlockedDestination("URL outside configured HTTPS host policy")
    return url


async def resolve_addresses(host, port):
    return await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, allowed_hosts, *, resolver=resolve_addresses, backend=None):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.resolve = resolver
        self.backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host not in self.allowed_hosts or port != 443:
            raise BlockedDestination("host/port outside policy")
        async with asyncio.timeout(timeout or 2):
            addresses = await self.resolve(host, port)
            if not addresses:
                raise BlockedDestination("empty DNS result")
            ips = [ipaddress.ip_address(row[4][0]) for row in addresses]
            if any(not ip.is_global or ip.is_multicast for ip in ips):
                raise BlockedDestination("DNS contains non-public address")
            # Connect to the approved numeric address. No second resolution of host.
            # HTTPCore retains original URL host for Host and TLS certificate/SNI.
            return await self.backend.connect_tcp(
                str(ips[0]), port, timeout=timeout, local_address=local_address,
                socket_options=socket_options,
            )

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


async def fetch_import_source(url, allowed_hosts):
    validate_url(url, allowed_hosts)
    backend = PinnedBackend(allowed_hosts)
    async with asyncio.timeout(10):
        async with httpcore.AsyncConnectionPool(network_backend=backend) as pool:
            async with pool.stream(
                "GET", url, headers={"Accept-Encoding": "identity"},
                extensions={"timeout": {"connect": 2, "read": 3, "write": 2, "pool": 2}},
            ) as response:
                if response.status != 200:
                    raise ValueError("upstream status rejected; redirects are not followed")
                encoding = next((v for k, v in response.headers if k.lower() == b"content-encoding"), b"identity")
                if encoding.lower() != b"identity":
                    raise ValueError("compressed response not supported by bounded importer")
                chunks, total = [], 0
                async for chunk in response.aiter_stream():
                    total += len(chunk)
                    if total > 1_000_000:
                        raise ValueError("upstream response exceeds byte budget")
                    chunks.append(chunk)
                return b"".join(chunks)
