import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from mealplanner import ai
from mealplanner.db import Database
from mealplanner.server import make_handler

KEY = "sk-ant-api03-" + "a" * 40 + "WXYZ"


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_save_mask_and_delete_key(self):
        status, settings = self.call("GET", "/api/settings")
        self.assertEqual((status, settings["api_key"]["set"]), (200, False))

        status, settings = self.call("PUT", "/api/settings", {"api_key": f"  {KEY}  "})
        self.assertEqual(status, 200)
        self.assertEqual(settings["api_key"], {"set": True, "hint": "sk-ant-…WXYZ", "env": settings["api_key"]["env"]})
        self.assertEqual(self.db.get_setting("anthropic_api_key"), KEY)

        # De volledige sleutel komt nergens in een antwoord terug.
        for response in (settings, self.call("GET", "/api/settings")[1]):
            self.assertNotIn(KEY, json.dumps(response))

        status, settings = self.call("DELETE", "/api/settings/api-key")
        self.assertEqual((status, settings["api_key"]["set"]), (200, False))
        self.assertIsNone(self.db.get_setting("anthropic_api_key"))

    def test_rejects_things_that_are_not_keys(self):
        for bad in ("", "hallo", "sk-ant-kort", "sk-proj-" + "a" * 40):
            self.assertEqual(self.call("PUT", "/api/settings", {"api_key": bad})[0], 400, bad)

    def test_ai_uses_key_from_settings(self):
        self.call("PUT", "/api/settings", {"api_key": KEY})
        self.assertEqual(ai._key_provider(), KEY)

    def test_connection_test_reports_problems(self):
        with mock.patch.object(ai, "check_connection", side_effect=ai.AIUnavailable(ai.NO_KEY)):
            status, result = self.call("POST", "/api/settings/test")
        self.assertEqual((status, result["error"]), (503, ai.NO_KEY))
        with mock.patch.object(ai, "check_connection", return_value=None):
            status, result = self.call("POST", "/api/settings/test")
        self.assertEqual((status, result["ok"]), (200, True))


@unittest.skipUnless(ai.sdk_installed(), "het anthropic-pakket is niet geïnstalleerd")
class MissingKeyTest(unittest.TestCase):
    def test_missing_key_gives_clear_message(self):
        ai.set_key_provider(lambda: None)
        with mock.patch.dict("os.environ", {}, clear=True):
            for call in (ai.check_connection, lambda: ai.generate_recipe("tosti", 1)):
                with self.assertRaises(ai.AIUnavailable) as ctx:
                    call()
                self.assertEqual(str(ctx.exception), ai.NO_KEY)


if __name__ == "__main__":
    unittest.main()
