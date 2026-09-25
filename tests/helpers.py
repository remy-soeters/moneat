"""Gedeelde hulp voor API-tests: een testserver met een ingelogde gebruiker."""

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from mealplanner import auth, netguard
from mealplanner.app import App, Config, make_handler
from mealplanner.db import Database
from mealplanner.images import ImageStore

# Snelle (onveilige) hashing in tests; de echte instelling staat in auth.py.
auth.SCRYPT_N = 2**8
# Tests draaien nep-websites op 127.0.0.1.
netguard.ALLOW_PRIVATE = True

PASSWORD = "een-lang-testwachtwoord"


class ApiClient:
    """Start de app op een vrije poort. Met `user` wordt er een account gemaakt en ingelogd."""

    def __init__(self, db=None, images=None, user="remy", admin=True, config=None):
        self.db = db or Database(":memory:")
        self.images = images or ImageStore(tempfile.mkdtemp())
        self.app = App(self.db, self.images, config or Config(quiet=True))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cookies = {}
        if user:
            self.db.create_user(user, auth.hash_password(PASSWORD), user.title(), is_admin=admin)
            status, _ = self.call("POST", "/api/auth/login", {"username": user, "password": PASSWORD})
            assert status == 200, status

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, method, path, body=None, raw=None, content_type="application/json", headers=None, csrf=True):
        """Geeft (status, headers, bytes)."""
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        all_headers = {"Content-Type": content_type}
        if csrf:
            all_headers["X-Requested-With"] = "mealplanner"
        if self.cookies:
            all_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        all_headers.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(req) as res:
                status, res_headers, content = res.status, res.headers, res.read()
        except urllib.error.HTTPError as e:
            status, res_headers, content = e.code, e.headers, e.read()
        for cookie in res_headers.get_all("Set-Cookie") or []:
            name, _, rest = cookie.partition("=")
            value = rest.split(";", 1)[0]
            if "Max-Age=0" in cookie:
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        return status, res_headers, content

    def call(self, method, path, body=None, **kwargs):
        """Geeft (status, json)."""
        status, _, content = self.request(method, path, body, **kwargs)
        return status, json.loads(content) if content else None


def api_test(case, **kwargs):
    """Maak in een TestCase een ingelogde client en ruim hem na afloop op."""
    client = ApiClient(**kwargs)
    case.addCleanup(client.close)
    return client
