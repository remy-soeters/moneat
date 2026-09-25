"""Inloggen, rechten en beveiliging van de webapp."""

import unittest
from unittest import mock

from mealplanner import auth, netguard
from mealplanner.app import Config
from tests.helpers import PASSWORD, ApiClient, api_test


class LoginTest(unittest.TestCase):
    def test_everything_needs_login(self):
        client = api_test(self, user=None)
        client.db.create_user("remy", auth.hash_password(PASSWORD), is_admin=True)
        self.assertEqual(client.call("GET", "/api/recipes"), (401, {"error": "Log eerst in", "login": True}))
        self.assertEqual(client.call("POST", "/api/recipes", {"name": "Soep"})[0], 401)
        self.assertEqual(client.request("GET", "/images/" + "a" * 32 + ".png")[0], 401)
        self.assertEqual(client.call("GET", "/api/health"), (200, {"ok": True}))
        status = client.call("GET", "/api/auth/status")[1]
        self.assertEqual((status["authenticated"], status["setup_required"]), (False, False))
        self.assertEqual(client.request("GET", "/")[0], 200)  # de app zelf (met inlogscherm) mag iedereen zien

    def test_login_logout_and_cookie_flags(self):
        client = api_test(self, user=None)
        client.db.create_user("remy", auth.hash_password(PASSWORD), "Remy", is_admin=True)
        self.assertEqual(client.call("POST", "/api/auth/login", {"username": "remy", "password": "fout"})[0], 401)
        self.assertEqual(client.call("POST", "/api/auth/login", {"username": "niemand", "password": "fout"})[0], 401)
        status, headers, _ = client.request("POST", "/api/auth/login", {"username": "Remy ", "password": PASSWORD})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        for flag in ("HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Secure", cookie)  # gewone http op het thuisnetwerk
        self.assertEqual(client.call("GET", "/api/recipes")[0], 200)
        stored = client.db.connect().__enter__().execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertNotIn(stored, cookie)  # alleen een hash van de sessiesleutel staat in de database

        client.call("POST", "/api/auth/logout", {})
        self.assertEqual(client.call("GET", "/api/recipes")[0], 401)

    def test_too_many_failures_block_for_a_while(self):
        client = api_test(self, user=None)
        client.db.create_user("remy", auth.hash_password(PASSWORD), is_admin=True)
        for _ in range(auth.MAX_FAILURES):
            client.call("POST", "/api/auth/login", {"username": "remy", "password": "fout"})
        status, body = client.call("POST", "/api/auth/login", {"username": "remy", "password": PASSWORD})
        self.assertEqual(status, 429)
        self.assertIn("Te veel mislukte pogingen", body["error"])

    def test_first_account_needs_code_from_log(self):
        client = api_test(self, user=None)
        self.assertTrue(client.call("GET", "/api/auth/status")[1]["setup_required"])
        account = {"username": "remy", "display_name": "Remy", "password": PASSWORD}
        self.assertEqual(client.call("POST", "/api/auth/setup", {**account, "code": "FOUT-CODE"})[0], 403)
        self.assertEqual(client.call("POST", "/api/auth/setup", {**account, "code": client.app.setup_code, "password": "kort"})[0], 400)
        status, body = client.call("POST", "/api/auth/setup", {**account, "code": client.app.setup_code.lower()})
        self.assertEqual((status, body["authenticated"], body["user"]["is_admin"]), (200, True, True))
        self.assertIsNone(client.app.setup_code)
        self.assertEqual(client.call("POST", "/api/auth/setup", {**account, "code": "X"})[0], 409)


class ProtectionTest(unittest.TestCase):
    def setUp(self):
        self.client = api_test(self)

    def test_changes_need_our_header_and_origin(self):
        self.assertEqual(self.client.call("POST", "/api/recipes", {"name": "Soep"}, csrf=False)[0], 403)
        foreign = {"Origin": "https://evil.example"}
        self.assertEqual(self.client.call("POST", "/api/recipes", {"name": "Soep"}, headers=foreign)[0], 403)
        same = {"Origin": self.client.base}
        self.assertEqual(self.client.call("POST", "/api/recipes", {"name": "Soep"}, headers=same)[0], 200)

    def test_security_headers(self):
        _, headers, _ = self.client.request("GET", "/")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertNotIn("Python", headers["Server"])
        self.assertIsNone(headers["Strict-Transport-Security"])  # alleen via https
        _, headers, _ = self.client.request("GET", "/api/recipes")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_behind_https_proxy_cookies_are_secure(self):
        client = ApiClient(user=None, config=Config(trust_proxy=True, quiet=True))
        self.addCleanup(client.close)
        client.db.create_user("remy", auth.hash_password(PASSWORD), is_admin=True)
        https = {"X-Forwarded-Proto": "https", "X-Real-IP": "203.0.113.9"}
        status, headers, _ = client.request("POST", "/api/auth/login", {"username": "remy", "password": PASSWORD}, headers=https)
        self.assertEqual(status, 200)
        self.assertTrue(headers["Set-Cookie"].startswith("__Host-mp_session="))
        self.assertIn("Secure", headers["Set-Cookie"])
        self.assertIn("max-age", headers["Strict-Transport-Security"])
        # De rem op raden werkt per echt IP-adres (uit X-Real-IP), niet per proxy.
        for _ in range(auth.MAX_FAILURES):
            client.call("POST", "/api/auth/login", {"username": "x", "password": "y"}, headers=https)
        other = {"X-Forwarded-Proto": "https", "X-Real-IP": "198.51.100.7"}
        self.assertEqual(client.call("POST", "/api/auth/login", {"username": "remy", "password": PASSWORD}, headers=other)[0], 200)

    def test_import_cannot_reach_home_network(self):
        with mock.patch.object(netguard, "ALLOW_PRIVATE", False):
            for url in ("http://127.0.0.1/", "http://192.168.1.1/", "http://localhost:8123/", "http://[::1]/", "file:///etc/passwd"):
                status, body = self.client.call("POST", "/api/recipes/import", {"url": url})
                self.assertIn(status, (422,), url)
                self.assertTrue("openbare websites" in body["error"] or "http- en https" in body["error"], body)

    def test_limits_on_input(self):
        self.assertEqual(self.client.call("POST", "/api/recipes", raw=b"x" * 1_100_000)[0], 413)
        self.assertEqual(self.client.call("POST", "/api/recipes", raw=b"[1, 2]")[0], 400)
        huge = {"name": "Soep", "ingredients": [{"name": f"ding {i}"} for i in range(150)]}
        self.assertEqual(self.client.call("POST", "/api/recipes", huge)[0], 400)
        self.assertEqual(self.client.call("POST", "/api/recipes", {"name": "x" * 500})[1]["name"], "x" * 150)


class RolesTest(unittest.TestCase):
    def setUp(self):
        self.admin = api_test(self)
        status, self.member_user = self.admin.call(
            "POST", "/api/users", {"username": "sam", "display_name": "Sam", "password": "nog-een-lang-wachtwoord"}
        )
        self.assertEqual(status, 200)
        self.member = ApiClient(user=None, db=self.admin.db, images=self.admin.images)
        self.addCleanup(self.member.close)
        self.assertEqual(self.member.call("POST", "/api/auth/login", {"username": "sam", "password": "nog-een-lang-wachtwoord"})[0], 200)

    def test_members_share_data_but_not_keys(self):
        self.admin.call("POST", "/api/recipes", {"name": "Soep"})
        self.assertEqual([r["name"] for r in self.member.call("GET", "/api/recipes")[1]], ["Soep"])
        settings = self.member.call("GET", "/api/settings")[1]
        self.assertEqual(settings["is_admin"], False)
        self.assertNotIn("claude", settings)
        self.assertEqual(self.member.call("PUT", "/api/settings", {"text_provider": "gemini"})[0], 403)
        self.assertEqual(self.member.call("GET", "/api/users")[0], 403)
        self.assertEqual(self.member.call("POST", "/api/bring/login", {})[0], 403)

    def test_admin_manages_accounts(self):
        users = self.admin.call("GET", "/api/users")[1]
        self.assertEqual([(u["username"], u["is_admin"], u["me"]) for u in users], [("remy", True, True), ("sam", False, False)])
        self.assertEqual(self.admin.call("POST", "/api/users", {"username": "kim", "password": "1234567890"})[0], 400)
        self.assertEqual(self.admin.call("POST", "/api/users", {"username": "Sam", "password": "weer-een-lang-wachtwoord"})[0], 400)
        me = next(u for u in users if u["me"])
        self.assertEqual(self.admin.call("DELETE", f"/api/users/{me['id']}")[0], 400)

        # Nieuw wachtwoord voor sam: sam is overal uitgelogd.
        self.admin.call("PUT", f"/api/users/{self.member_user['id']}", {"password": "een-heel-nieuw-wachtwoord"})
        self.assertEqual(self.member.call("GET", "/api/recipes")[0], 401)
        self.assertEqual(self.admin.call("DELETE", f"/api/users/{self.member_user['id']}")[1], {"ok": True})

    def test_change_own_password(self):
        wrong = {"current": "fout", "new": "mijn-nieuwe-wachtwoord"}
        self.assertEqual(self.member.call("PUT", "/api/auth/password", wrong)[0], 403)
        other_device = ApiClient(user=None, db=self.admin.db, images=self.admin.images)
        self.addCleanup(other_device.close)
        other_device.call("POST", "/api/auth/login", {"username": "sam", "password": "nog-een-lang-wachtwoord"})
        change = {"current": "nog-een-lang-wachtwoord", "new": "mijn-nieuwe-wachtwoord"}
        self.assertEqual(self.member.call("PUT", "/api/auth/password", change)[0], 200)
        self.assertEqual(self.member.call("GET", "/api/recipes")[0], 200)  # dit apparaat blijft ingelogd
        self.assertEqual(other_device.call("GET", "/api/recipes")[0], 401)  # andere apparaten niet


class PasswordTest(unittest.TestCase):
    def test_hashing(self):
        stored = auth.hash_password("een-goed-wachtwoord")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertTrue(auth.verify_password("een-goed-wachtwoord", stored))
        self.assertFalse(auth.verify_password("een-ander-wachtwoord", stored))
        self.assertFalse(auth.verify_password("x", "rommel"))
        self.assertNotEqual(stored, auth.hash_password("een-goed-wachtwoord"))  # eigen zout per hash

    def test_rules(self):
        for bad in ("kort", "1234567890", "remy-de-kok", "x" * 300):
            with self.assertRaises(ValueError):
                auth.check_new_password(bad, "remy-de-kok")
        self.assertEqual(auth.check_new_password("lekker eten elke dag"), "lekker eten elke dag")

    def test_throttle_releases_after_lockout(self):
        now = [0.0]
        throttle = auth.Throttle(max_failures=2, window=60, lockout=100, clock=lambda: now[0])
        throttle.failure("ip:1")
        throttle.check("ip:1")
        throttle.failure("ip:1")
        with self.assertRaises(auth.AuthError):
            throttle.check("ip:1")
        now[0] = 101
        throttle.check("ip:1")


if __name__ == "__main__":
    unittest.main()
