"""Veilig webpagina's ophalen voor de recepten-import.

Omdat iedereen die inlogt een link kan laten ophalen, mag de server daarbij nooit het eigen netwerk in:
geen router, NAS, Home Assistant of beheerpagina's (SSRF). Daarom:
- alleen http(s) op de standaardpoorten 80 en 443;
- het IP-adres wordt vóór het verbinden gecontroleerd, en we verbinden precies met dat gecontroleerde adres
  (dus een DNS-truc tussen controleren en verbinden werkt niet);
- elke doorverwijzing gaat opnieuw door dezelfde controle.
"""

import http.client
import ipaddress
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

ALLOWED_PORTS = {80, 443}
# Alleen voor tests en lokaal ontwikkelen: ook adressen op het eigen netwerk toestaan.
ALLOW_PRIVATE = False


class BlockedAddress(urllib.error.URLError):
    def __init__(self, host):
        super().__init__(f"{host} is geen openbaar internetadres")
        self.host = host


def is_public(ip):
    ip = ipaddress.ip_address(ip)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url):
    """Controleer schema en poort van een URL (het adres zelf wordt bij het verbinden gecontroleerd)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedAddress(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS and not ALLOW_PRIVATE:
        raise BlockedAddress(f"{parts.hostname}:{port}")
    return url


def _connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, **_):
    host, port = address
    if port not in ALLOWED_PORTS and not ALLOW_PRIVATE:
        raise BlockedAddress(f"{host}:{port}")
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    allowed = [info for info in infos if ALLOW_PRIVATE or is_public(info[4][0])]
    if not allowed:
        raise BlockedAddress(host)
    error = None
    for family, kind, proto, _, sockaddr in allowed:
        sock = socket.socket(family, kind, proto)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            error = e
            sock.close()
    raise error


# http.client zet `_create_connection` per verbinding in __init__, dus pas daarna overschrijven.
class _HTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect


class _HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSConnection, req, context=self._context)


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    # Bewust zelf samengesteld: geen proxy-, file:- of ftp:-ondersteuning zoals in de standaard-opener.
    opener = urllib.request.OpenerDirector()
    for handler in (
        _HTTPHandler(),
        _HTTPSHandler(context=ssl.create_default_context()),
        _RedirectHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


def urlopen(request, timeout):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    check_url(url)
    try:
        return _opener().open(request, timeout=timeout)
    except urllib.error.URLError as e:
        # urllib verpakt fouten bij het verbinden in een URLError; haal onze blokkade eruit.
        if isinstance(e.reason, BlockedAddress):
            raise e.reason from None
        raise
