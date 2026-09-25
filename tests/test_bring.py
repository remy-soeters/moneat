import json
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests.helpers import ApiClient, api_test
from mealplanner import bring
from mealplanner.db import Database
from mealplanner.setting_keys import BRING_AUTH as BRING_SETTING

ARTICLES = {"Zwiebeln": "Uien", "Tomaten": "Tomaten", "Milch": "Melk"}


class FakeBring(BaseHTTPRequestHandler):
    """Doet zich voor als de (onofficiële) Bring!-API."""

    state = {}

    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        if self.path == "/rest/v2/bringauth":
            FakeBring.state["logins"].append(form)
            if form.get("password") != ["geheim"]:
                return self._reply(401, {"message": "wrong"})
            return self._reply(200, {"uuid": "user-1", "publicUuid": "pub-1", "access_token": "token-1",
                                     "refresh_token": "refresh-1", "expires_in": 3600, "bringListUUID": "list-home"})
        if self.path == "/rest/v2/bringauth/token":
            FakeBring.state["refreshes"] += 1
            return self._reply(200, {"access_token": "token-2", "expires_in": 3600})
        self._reply(404, {})

    def do_GET(self):
        if self.path == "/locale/articles.nl-NL.json":
            return self._reply(200, ARTICLES)
        if not self._authorized():
            return self._reply(401, {})
        if self.path == "/rest/bringusers/user-1/lists":
            return self._reply(200, {"lists": [{"listUuid": "list-home", "name": "Thuis"},
                                               {"listUuid": "list-bbq", "name": "BBQ"}]})
        if self.path.startswith("/rest/v2/bringlists/"):
            items = [{"itemId": name, "specification": ""} for name in sorted(FakeBring.state["purchase"])]
            return self._reply(200, {"items": {"purchase": items, "recently": []}})
        self._reply(404, {})

    def do_PUT(self):
        if not self._authorized():
            return self._reply(401, {})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeBring.state["puts"].append((self.path, body))
        for change in body["changes"]:
            if change["operation"] == "TO_PURCHASE":
                FakeBring.state["purchase"][change["itemId"]] = change["spec"]
            else:
                FakeBring.state["purchase"].pop(change["itemId"], None)
        self._reply(204, None)

    def _authorized(self):
        return self.headers.get("Authorization") in ("Bearer token-1", "Bearer token-2") and \
            self.headers.get("X-BRING-USER-UUID") == "user-1"

    def _reply(self, status, payload):
        data = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class BringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeBring)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.fake.server_address[1]}"
        cls.patches = [mock.patch.object(bring, "BASE_URL", base + "/rest"),
                       mock.patch.object(bring, "LOCALES_URL", base + "/locale"),
                       mock.patch.object(bring, "_catalog", None)]
        for patch in cls.patches:
            patch.start()

    @classmethod
    def tearDownClass(cls):
        for patch in cls.patches:
            patch.stop()
        cls.fake.shutdown()
        cls.fake.server_close()

    def setUp(self):
        FakeBring.state = {"logins": [], "refreshes": 0, "puts": [], "purchase": {"Brood": ""}}
        self.db = Database(":memory:")
        self.api = api_test(self, db=self.db)
        self.base = self.api.base

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def login(self):
        return self.call("POST", "/api/bring/login", {"email": "remy@example.com", "password": "geheim"})

    def test_login_keeps_tokens_but_not_password(self):
        status, res = self.login()
        self.assertEqual(status, 200)
        self.assertEqual((res["list_name"], [l["name"] for l in res["lists"]]), ("Thuis", ["Thuis", "BBQ"]))
        stored = self.db.get_setting(BRING_SETTING)
        self.assertIn("refresh-1", stored)
        self.assertNotIn("geheim", stored)
        self.assertTrue(self.call("GET", "/api/settings")[1]["bring"]["connected"])
        self.assertTrue(self.call("GET", "/api/shopping")[1]["bring"])

    def test_wrong_password_is_explained(self):
        status, res = self.call("POST", "/api/bring/login", {"email": "remy@example.com", "password": "fout"})
        self.assertEqual(status, 502)
        self.assertIn("wachtwoord klopt niet", res["error"])
        self.assertIsNone(self.db.get_setting(BRING_SETTING))

    def test_sync_sends_list_and_checks_off_what_is_done(self):
        self.login()
        self.db.add_shopping_item("ui", 2, "")
        self.db.add_shopping_item("Tomaat", 500, "g")
        self.db.add_shopping_item("Tomaat", 1, "blik")
        self.db.add_shopping_item("Boerenkool", 1.5, "kg")
        status, res = self.call("POST", "/api/bring/sync", {})
        self.assertEqual((status, res["sent"], res["checked_off"], res["list_name"]), (200, 3, 0, "Thuis"))
        self.assertEqual(FakeBring.state["puts"][-1][0], "/rest/v2/bringlists/list-home/items")
        self.assertEqual(FakeBring.state["purchase"], {
            "Brood": "", "Zwiebeln": "2", "Tomaten": "500 g + 1 blik", "Boerenkool": "1,5 kg",
        })

        key = next(i["key"] for i in self.db.shopping_list() if i["name"] == "Ui")
        self.db.set_shopping_check(key, True)
        res = self.call("POST", "/api/bring/sync", {})[1]
        self.assertEqual((res["sent"], res["checked_off"]), (2, 1))
        self.assertNotIn("Zwiebeln", FakeBring.state["purchase"])
        self.assertIn("Brood", FakeBring.state["purchase"])  # zelf in Bring! gezet: blijft staan

    def test_choose_list_and_disconnect(self):
        self.login()
        self.assertEqual(self.call("PUT", "/api/bring/list", {"list_uuid": "list-bbq"})[1]["list_name"], "BBQ")
        self.assertEqual(self.call("PUT", "/api/bring/list", {"list_uuid": "bestaat-niet"})[0], 400)
        self.db.add_shopping_item("Melk", 1, "l")
        self.call("POST", "/api/bring/sync", {})
        self.assertEqual(FakeBring.state["puts"][-1][0], "/rest/v2/bringlists/list-bbq/items")
        self.assertFalse(self.call("DELETE", "/api/bring")[1]["connected"])
        self.assertEqual(self.call("POST", "/api/bring/sync", {})[0], 400)

    def test_expired_access_is_renewed(self):
        self.login()
        auth = json.loads(self.db.get_setting(BRING_SETTING))
        auth["expires_at"] = time.time() - 10
        self.db.set_setting(BRING_SETTING, json.dumps(auth))
        self.assertEqual(self.call("POST", "/api/bring/sync", {})[0], 200)
        self.assertEqual(FakeBring.state["refreshes"], 1)
        self.assertIn("token-2", self.db.get_setting(BRING_SETTING))


if __name__ == "__main__":
    unittest.main()
