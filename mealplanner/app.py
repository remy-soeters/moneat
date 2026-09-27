"""De webapp: koppelt de database, achtergrondtaken en routes aan elkaar, met inloggen en beveiliging.

Elk verzoek gaat door `App.handle`:
1. API-verzoeken die iets veranderen moeten van de eigen site komen (bescherming tegen CSRF);
2. de sessie-cookie bepaalt wie er is ingelogd;
3. de route wordt uitgevoerd, fouten worden nette meldingen;
4. elk antwoord krijgt beveiligingskoppen mee.
"""

import hashlib
import json
import mimetypes
import os
import sys
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from . import ai, auth, routes, setting_keys
from .actions import describe_action
from .db import NotFound
from .icons import IconMaker
from .importer import ImportFailed
from .preloader import DEFAULT_PRELOAD, PRELOAD_OPTIONS, SwipePreloader
from .web import SECURITY_HEADERS, ApiError, Request, Response, Router, cookie_header
from .writer import RecipeWriter

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "mealplanner"

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")


@dataclass
class Config:
    # Staat de app achter een proxy (Nginx Proxy Manager)? Dan vertrouwen we X-Forwarded-Proto/-For/X-Real-IP.
    trust_proxy: bool = False
    static_dir: Path = field(default_factory=lambda: STATIC_DIR)
    quiet: bool = False  # geen regel per verzoek in het log (tests)

    @classmethod
    def from_env(cls):
        return cls(trust_proxy=os.environ.get("MEALPLANNER_PROXY", "").strip().lower() in ("1", "true", "yes", "ja"))


class App:
    def __init__(self, db, images, config=None):
        self.db = db
        self.images = images
        self.config = config or Config()
        ai.set_settings(db.get_setting)
        self.preloader = SwipePreloader(db, images, self.release_image, self.load_preferences, self.preload_target)
        self.icon_maker = IconMaker(db, images)
        self.writer = RecipeWriter(db, self.log_error)
        self.writer.kick()  # schetsen die de vorige keer nog niet uitgeschreven waren
        self.throttle = auth.Throttle()
        # Nog niemand? Dan kan het eerste account alleen met deze code uit het serverlog worden gemaakt.
        self.setup_code = auth.new_setup_code() if db.count_users() == 0 else None
        self.router = Router()
        routes.register_all(self.router, self)

    # ---------- gedeelde hulpfuncties voor de routes ----------

    def load_preferences(self):
        try:
            return json.loads(self.db.get_setting(setting_keys.PREFERENCES) or "{}")
        except ValueError:
            return {}

    def release_image(self, url):
        """Verwijder een foto van schijf zodra geen recept of voorstel hem meer gebruikt."""
        if url and not self.db.image_in_use(url):
            self.images.delete(url)

    def log_error(self, source, action, message, detail="", user="", when=None):
        """Bewaar wat er misging, zodat je het bij Instellingen → Foutmeldingen kunt teruglezen (en in het serverlog)."""
        if not self.config.quiet:
            sys.stderr.write(f"FOUT {source} · {action}: {message}{f' | {detail}' if detail else ''}\n")
        try:
            self.db.log_error(source, action, message, detail, user, when)
        except Exception:
            traceback.print_exc()  # het logboek mag de melding zelf nooit in de weg zitten

    def preload_target(self):
        try:
            value = int(self.db.get_setting(setting_keys.SWIPE_PRELOAD) or DEFAULT_PRELOAD)
        except ValueError:
            value = DEFAULT_PRELOAD
        return value if value in PRELOAD_OPTIONS else DEFAULT_PRELOAD

    # ---------- sessies ----------

    def cookie_name(self, req):
        return auth.SECURE_COOKIE if req.secure else auth.COOKIE

    def start_session(self, req, user):
        token = auth.new_token()
        req.session_hash = auth.token_hash(token)
        self.db.create_session(req.session_hash, user["id"], auth.session_expiry(), req.headers.get("User-Agent"))
        req.cookies_to_set.append(
            cookie_header(self.cookie_name(req), token, max_age=auth.SESSION_DAYS * 86400, secure=req.secure)
        )
        req.user = user

    def end_session(self, req):
        if req.session_hash:
            self.db.delete_session(req.session_hash)
        req.cookies_to_set.append(cookie_header(self.cookie_name(req), "", max_age=0, secure=req.secure))
        req.user = None
        req.session_hash = None

    def _authenticate(self, req):
        token = req.cookie(self.cookie_name(req))
        if not token or len(token) > 100:
            return
        token_hash = auth.token_hash(token)
        user, last_seen = self.db.session_user(token_hash)
        if user is None:
            return
        req.user, req.session_hash = user, token_hash
        if auth.needs_refresh(last_seen):  # blijf ingelogd zolang je de app gebruikt
            self.db.extend_session(token_hash, auth.session_expiry())
            req.cookies_to_set.append(
                cookie_header(self.cookie_name(req), token, max_age=auth.SESSION_DAYS * 86400, secure=req.secure)
            )

    # ---------- verzoeken afhandelen ----------

    def handle(self, req):
        if req.path.startswith("/api/"):
            response = self._api(req)
            response.headers.append(("Cache-Control", "no-store"))
        elif req.path.startswith("/images/"):
            response = self._image(req)
        else:
            response = self._static(req)
        response.headers.extend(SECURITY_HEADERS)
        if req.secure:
            response.headers.append(("Strict-Transport-Security", "max-age=31536000"))
        response.headers.extend(("Set-Cookie", c) for c in req.cookies_to_set)
        return response

    def _api(self, req):
        try:
            if req.method not in ("GET", "HEAD"):
                self._check_same_origin(req)
            self._authenticate(req)
            route, args = self.router.match(req.method, req.path)
            if route.auth and req.user is None:
                return Response.error(HTTPStatus.UNAUTHORIZED, "Log eerst in", login=True)
            if route.admin and not req.user["is_admin"]:
                return Response.error(HTTPStatus.FORBIDDEN, "Alleen een beheerder kan dit")
            result = route.handler(req, *args)
            return result if isinstance(result, Response) else Response.json(result)
        except ApiError as e:
            return Response.error(e.status, str(e))
        except auth.AuthError as e:
            return Response.error(e.status, str(e))
        except NotFound as e:
            return Response.error(HTTPStatus.NOT_FOUND, str(e))
        except ai.AIUnavailable as e:
            self._log_request_error(req, e.source or ai.provider_name(), str(e), e.detail)
            return Response.error(HTTPStatus.SERVICE_UNAVAILABLE, str(e))
        except ImportFailed as e:
            self._log_request_error(req, "Importeren", str(e))
            return Response.error(HTTPStatus.UNPROCESSABLE_ENTITY, str(e))
        except ValueError as e:
            return Response.error(HTTPStatus.BAD_REQUEST, str(e) or "Ongeldige invoer")
        except Exception:
            traceback.print_exc()
            self._log_request_error(req, "Server", "Interne serverfout", traceback.format_exc()[-4000:])
            return Response.error(HTTPStatus.INTERNAL_SERVER_ERROR, "Interne serverfout")

    def _log_request_error(self, req, source, message, detail=""):
        user = (req.user or {}).get("display_name", "")
        self.log_error(source, describe_action(req.method, req.path), message, detail, user)

    def _check_same_origin(self, req):
        """Wijzigingen alleen vanaf de eigen site: een eigen kop (die andere sites niet kunnen meesturen
        zonder toestemming) plus, als de browser hem meestuurt, een Origin die bij deze host hoort."""
        if req.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise ApiError(HTTPStatus.FORBIDDEN, "Verzoek geweigerd (ontbrekende beveiligingskop)")
        origin = req.headers.get("Origin")
        if origin:
            host = (req.headers.get("Host") or "").lower()
            if urlparse(origin).netloc.lower() != host:
                raise ApiError(HTTPStatus.FORBIDDEN, "Verzoek geweigerd (andere website)")

    def _image(self, req):
        if req.method not in ("GET", "HEAD"):
            return Response.error(HTTPStatus.METHOD_NOT_ALLOWED, "Niet toegestaan")
        self._authenticate(req)
        if req.user is None:
            return Response.error(HTTPStatus.UNAUTHORIZED, "Log eerst in", login=True)
        file = self.images.path_for(req.path)
        if file is None:
            return Response.error(HTTPStatus.NOT_FOUND, "Afbeelding niet gevonden")
        return Response(
            HTTPStatus.OK, file.read_bytes(), self.images.content_type(file),
            [("Cache-Control", "private, max-age=31536000, immutable")],
        )

    def _static(self, req):
        """Bestanden van de app. index.html verwijst naar /v/<versie>/css/… en /v/<versie>/js/…: elke versie van
        de app heeft zo eigen adressen, zodat een browser of proxy (bijv. Nginx Proxy Manager met "Cache Assets")
        na een update nooit oude scripts combineert met de nieuwe pagina."""
        if req.method not in ("GET", "HEAD"):
            return Response.error(HTTPStatus.METHOD_NOT_ALLOWED, "Niet toegestaan")
        static = self.config.static_dir.resolve()
        path, versioned = req.path, False
        if path.startswith("/v/"):
            version, _, rest = path[3:].partition("/")
            path, versioned = "/" + rest, version == self.asset_version()
        path = path if path not in ("", "/") else "/index.html"
        file = (static / path.lstrip("/")).resolve()
        hidden = any(part.startswith(".") for part in file.relative_to(static).parts) if file.is_relative_to(static) else True
        if hidden or not file.is_file():
            # Onbekende paden (bijv. /boodschappen na verversen) tonen gewoon de app.
            file = static / "index.html"
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/manifest+json"):
            content_type += "; charset=utf-8"
        body = file.read_bytes()
        if file.name == "index.html":
            prefix = f"/v/{self.asset_version()}"
            body = body.replace(b'href="/css/', f'href="{prefix}/css/'.encode()).replace(
                b'src="/js/', f'src="{prefix}/js/'.encode()
            )
            return Response(HTTPStatus.OK, body, content_type, [("Cache-Control", "no-cache")])
        cache = "public, max-age=31536000, immutable" if versioned else "no-cache"
        return Response(HTTPStatus.OK, body, content_type, [("Cache-Control", cache)])

    def asset_version(self):
        """Korte vingerafdruk van alle bestanden in static/ (naam, grootte, tijd): verandert bij elke update."""
        static = self.config.static_dir
        stamp = sorted(
            (str(f.relative_to(static)), f.stat().st_size, f.stat().st_mtime_ns)
            for f in static.rglob("*") if f.is_file()
        )
        return hashlib.sha256(repr(stamp).encode()).hexdigest()[:10]


def make_handler(app):
    trust_proxy = app.config.trust_proxy

    class Handler(BaseHTTPRequestHandler):
        def version_string(self):
            return "mealplanner"  # geen Python-versie in de Server-kop
        timeout = 30  # stille of hangende verbindingen niet eindeloos openhouden
        protocol_version = "HTTP/1.1"

        def _serve(self):
            req = Request(self, trust_proxy=trust_proxy)
            try:
                response = app.handle(req)
            except Exception:
                traceback.print_exc()
                response = Response.error(HTTPStatus.INTERNAL_SERVER_ERROR, "Interne serverfout")
            self._client_ip = req.client_ip
            # Niet gelezen body (bijv. bij een geweigerd verzoek) weggooien, anders raakt de verbinding in de war.
            if req._body is None and self.command not in ("GET", "HEAD"):
                self.close_connection = True
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _serve

        def log_error(self, format, *args):
            if "timed out" not in format % args:  # een stille verbinding sluiten is normaal, geen fout
                self.log_message(format, *args)

        def log_message(self, format, *args):
            if app.config.quiet:
                return
            sys.stderr.write(f"{getattr(self, '_client_ip', self.client_address[0])} - {format % args}\n")

    return Handler
