"""HTTP transport for crawling public sites without accessing internal networks.

Check DNS answers at socket creation, then connect to the checked sockaddr
without a second lookup. Keep the original hostname for HTTP Host and TLS
certificate verification. Requests redirects use the same guarded transport.
"""

import ipaddress
import socket
import sys
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
from urllib3.util.timeout import _DEFAULT_TIMEOUT


# Translation/tunnel addresses can embed an otherwise blocked IPv4 target.
IPV6_TRANSITION_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32",
))


class BlockedRequest(requests.exceptions.RequestException):
    """A crawl request tried to access a non-public destination."""


class UnsafeDestination(Exception):
    """Non-retryable socket rejection, distinct from urllib3's OSError paths."""


def require_public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise UnsafeDestination("SSRF_BLOCKED: invalid destination IP") from exc
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        elif any(address in network for network in IPV6_TRANSITION_NETWORKS):
            raise UnsafeDestination("SSRF_BLOCKED: IPv6 transition destination")
    if (
        not address.is_global or address.is_multicast or address.is_reserved
        or address.is_unspecified or "%" in value
    ):
        raise UnsafeDestination(f"SSRF_BLOCKED: non-public destination {value}")


class PublicConnectionMixin:
    def _new_conn(self):
        if self._tunnel_host is not None:
            raise UnsafeDestination("SSRF_BLOCKED: HTTP tunnels are disabled")
        try:
            answers = socket.getaddrinfo(
                self._dns_host, self.port, socket.AF_UNSPEC, socket.SOCK_STREAM,
            )
            if not answers:
                raise OSError("DNS returned no addresses")
            # Reject mixed public/private answers before opening any socket.
            for _, _, _, _, sockaddr in answers:
                require_public_ip(sockaddr[0])

            last_error = None
            for family, socktype, protocol, _, sockaddr in answers:
                sock = None
                try:
                    sock = socket.socket(family, socktype, protocol)
                    for option in self.socket_options or ():
                        sock.setsockopt(*option)
                    if self.timeout is not _DEFAULT_TIMEOUT:
                        sock.settimeout(self.timeout)
                    if self.source_address:
                        sock.bind(self.source_address)
                    # sockaddr came from the validated DNS snapshot. Do not
                    # call create_connection(hostname), which resolves again.
                    sock.connect(sockaddr)
                    sys.audit("http.client.connect", self, self.host, self.port)
                    return sock
                except OSError as exc:
                    last_error = exc
                    if sock is not None:
                        sock.close()
            raise last_error
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except socket.timeout as exc:
            raise ConnectTimeoutError(
                self, f"Connection timed out (connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a connection: {exc}") from exc


class PublicHTTPConnection(PublicConnectionMixin, HTTPConnection):
    pass


class PublicHTTPSConnection(PublicConnectionMixin, HTTPSConnection):
    pass


class PublicHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = PublicHTTPConnection


class PublicHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = PublicHTTPSConnection


class PublicHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        # Use an instance mapping; do not alter urllib3's global pool classes.
        self.poolmanager.pool_classes_by_scheme = {
            "http": PublicHTTPConnectionPool,
            "https": PublicHTTPSConnectionPool,
        }

    def send(self, request, **kwargs):
        try:
            parsed = urlsplit(request.url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("HTTP(S) hostname required")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("URL credentials are disabled")
            parsed.port  # Validate malformed port numbers before connecting.
        except ValueError as exc:
            raise BlockedRequest("SSRF_BLOCKED: invalid crawl URL") from exc
        try:
            return super().send(request, **kwargs)
        except UnsafeDestination as exc:
            raise BlockedRequest(str(exc), request=request) from exc

    def proxy_manager_for(self, *args, **kwargs):
        # A proxy would resolve/connect elsewhere, bypassing our socket guard.
        raise BlockedRequest("SSRF_BLOCKED: crawl proxies are disabled")


def create_public_session():
    session = requests.Session()
    session.trust_env = False  # Ignore environment proxies and .netrc credentials.
    session.mount("http://", PublicHTTPAdapter())
    session.mount("https://", PublicHTTPAdapter())
    return session
