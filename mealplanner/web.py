"""Een klein webframework bovenop http.server: verzoeken, antwoorden, routes en beveiligingskoppen."""

import json
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

MAX_JSON_BODY = 1_000_000


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ---------- verzoek ----------


class Request:
    def __init__(self, handler, trust_proxy=False):
        self._handler = handler
        url = urlparse(handler.path)
        self.method = handler.command
        self.path = url.path
        self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        self.headers = handler.headers
        self.user = None
        self.session_hash = None
        self.cookies_to_set = []
        self._body = None

        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        self.scheme = forwarded_proto if trust_proxy and forwarded_proto in ("http", "https") else "http"
        self.client_ip = handler.client_address[0]
        if trust_proxy:
            # Nginx Proxy Manager zet X-Real-IP; anders het laatste adres dat de proxy zelf toevoegde.
            forwarded_for = [ip.strip() for ip in (self.headers.get("X-Forwarded-For") or "").split(",") if ip.strip()]
            self.client_ip = (self.headers.get("X-Real-IP") or "").strip() or (forwarded_for[-1] if forwarded_for else self.client_ip)

    @property
    def secure(self):
        return self.scheme == "https"

    def cookie(self, name):
        # Zelf uitlezen: één vreemde cookie van een andere app op hetzelfde domein mag de rest niet breken.
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value.strip().strip('"') or None
        return None

    def body(self, limit=MAX_JSON_BODY):
        if self._body is None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Ongeldige Content-Length") from None
            if length < 0:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Ongeldige Content-Length")
            if length > limit:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Verzoek is te groot")
            self._body = self._handler.rfile.read(length) if length else b""
        return self._body

    def json(self):
        try:
            data = json.loads(self.body() or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Ongeldige JSON") from None
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Verwacht een JSON-object")
        return data

    def param(self, name):
        value = self.query.get(name)
        if not value:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"Parameter '{name}' ontbreekt")
        return value


# ---------- antwoord ----------


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json; charset=utf-8"
    headers: list = field(default_factory=list)

    @classmethod
    def json(cls, payload, status=HTTPStatus.OK):
        return cls(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    @classmethod
    def error(cls, status, message, **extra):
        return cls.json({"error": message, **extra}, status)


def cookie_header(name, value, *, max_age, secure):
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={int(max_age)}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


# ---------- routes ----------


@dataclass
class Route:
    method: str
    pattern: re.Pattern
    handler: object
    auth: bool = True  # alleen voor ingelogde gebruikers
    admin: bool = False  # alleen voor beheerders


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, path, handler, **options):
        self.routes.append(Route(method, re.compile(path), handler, **options))

    def route(self, method, path, **options):
        def decorate(handler):
            self.add(method, path, handler, **options)
            return handler
        return decorate

    def get(self, path, **options):
        return self.route("GET", path, **options)

    def post(self, path, **options):
        return self.route("POST", path, **options)

    def put(self, path, **options):
        return self.route("PUT", path, **options)

    def delete(self, path, **options):
        return self.route("DELETE", path, **options)

    def match(self, method, path):
        allowed = False
        for route in self.routes:
            found = route.pattern.fullmatch(path)
            if found:
                if route.method == method or (method == "HEAD" and route.method == "GET"):
                    return route, found.groups()
                allowed = True
        if allowed:
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Deze methode is hier niet toegestaan")
        raise ApiError(HTTPStatus.NOT_FOUND, "Onbekend API-pad")


# ---------- beveiligingskoppen ----------

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    # Inline style-attributen (achtergrondfoto's, kleuren) en de lettertypen van Google Fonts.
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SECURITY_HEADERS = [
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
]
