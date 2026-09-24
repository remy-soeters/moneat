import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from mealplanner import ai, gemini
from mealplanner.db import Database
from mealplanner.images import ImageStore
from mealplanner.server import make_handler
from tests.test_import import tiny_png

RECIPE = {"name": "Pompoensoep", "servings": 2, "prep_minutes": 30, "tags": "soep", "instructions": "1. Koken.",
          "ingredients": [{"name": "pompoen", "quantity": 500, "unit": "g"}]}


class FakeGemini(BaseHTTPRequestHandler):
    """Doet zich voor als de Gemini Interactions API."""

    requests = []
    mode = "ok"

    def do_GET(self):
        self._reply(200, {"models": [{"name": "models/gemini-3.8-flash"}, {"name": "models/gemini-3.1-flash-lite-image"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeGemini.requests.append((self.headers["x-goog-api-key"], body))
        if FakeGemini.mode == "bad-key":
            return self._reply(403, {"error": {"message": "API key not valid"}})
        if FakeGemini.mode == "billing":
            return self._reply(429, {"error": {"message": "Image generation is not available on the free tier"}})
        if body["response_format"]["type"] == "image":
            data = base64.b64encode(tiny_png()).decode()
            content = [{"type": "image", "data": data, "mime_type": "image/png"}]
        else:
            content = [{"type": "text", "text": json.dumps(RECIPE)[:20]}, {"type": "text", "text": json.dumps(RECIPE)[20:]}]
        self._reply(200, {"status": "completed", "steps": [{"type": "thought"}, {"type": "model_output", "content": content}]})

    def _reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class GeminiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeGemini)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        cls.base_patch = mock.patch.object(gemini, "BASE_URL", f"http://127.0.0.1:{cls.fake.server_address[1]}/v1beta")
        cls.base_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.base_patch.stop()
        cls.fake.shutdown()
        cls.fake.server_close()

    def setUp(self):
        FakeGemini.requests.clear()
        FakeGemini.mode = "ok"
        self.settings = {ai.GEMINI_KEY: "test-key", ai.TEXT_PROVIDER: "gemini"}
        ai.set_settings(lambda key, default=None: self.settings.get(key, default))

    def tearDown(self):
        ai.set_settings(lambda key, default=None: default)

    def test_recipe_text_goes_to_gemini_with_schema(self):
        recipe = ai.generate_recipe("pompoensoep", 2)
        self.assertEqual(recipe["name"], "Pompoensoep")  # tekst over twee blokken samengevoegd
        key, body = FakeGemini.requests[0]
        self.assertEqual((key, body["model"], body["store"]), ("test-key", gemini.DEFAULT_TEXT_MODEL, False))
        self.assertEqual(body["response_format"]["schema"], ai.NEW_RECIPE_SCHEMA)
        self.assertIn("pompoensoep", body["input"])

    def test_photo(self):
        data = ai.generate_photo(RECIPE)
        self.assertTrue(data.startswith(b"\x89PNG"))
        _, body = FakeGemini.requests[0]
        self.assertEqual(body["model"], gemini.DEFAULT_IMAGE_MODEL)
        self.assertIn("Pompoensoep", body["input"][0]["text"])
        self.assertIn("pompoen", body["input"][0]["text"])

    def test_clear_errors(self):
        FakeGemini.mode = "bad-key"
        with self.assertRaisesRegex(ai.AIUnavailable, "niet geaccepteerd"):
            ai.generate_recipe("soep")
        FakeGemini.mode = "billing"
        with self.assertRaisesRegex(ai.AIUnavailable, "betalen nodig"):
            ai.generate_photo(RECIPE)
        self.settings.pop(ai.GEMINI_KEY)
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ai.AIUnavailable, "Gemini API-sleutel"):
                ai.generate_photo(RECIPE)

    def test_connection_check_reports_missing_models(self):
        ai.check_gemini()
        self.settings[ai.GEMINI_IMAGE_MODEL] = "gemini-bestaat-niet"
        with self.assertRaisesRegex(ai.AIUnavailable, "gemini-bestaat-niet"):
            ai.check_gemini()


class PhotoRoutesTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db, self.images))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.photo = mock.patch.object(ai, "generate_photo", return_value=tiny_png())
        self.photo.start()

    def tearDown(self):
        self.photo.stop()
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

    def test_photo_for_recipe_replaces_old_one(self):
        recipe = self.db.create_recipe(RECIPE)
        _, first = self.call("POST", f"/api/recipes/{recipe['id']}/photo")
        _, second = self.call("POST", f"/api/recipes/{recipe['id']}/photo")
        self.assertIsNone(self.images.path_for(first["image"]))
        self.assertIsNotNone(self.images.path_for(second["image"]))
        self.assertEqual(self.db.get_recipe(recipe["id"])["image"], second["image"])
        self.assertEqual(len(self.db.get_recipe(recipe["id"])["ingredients"]), 1)

    def test_photo_for_draft(self):
        status, result = self.call("POST", "/api/photos/draft", {"recipe": RECIPE})
        self.assertEqual(status, 200)
        self.assertIsNotNone(self.images.path_for(result["image"]))
        self.assertEqual(self.call("POST", "/api/photos/draft", {"recipe": {}})[0], 400)

    def test_photo_for_inspiration_is_kept_with_the_idea(self):
        self.db.save_inspiration("herfst|2", {"intro": "", "ideas": [{"description": "", "recipe": dict(RECIPE)}]})
        status, result = self.call("POST", "/api/inspiration/photo", {"theme": "Herfst", "servings": 2, "index": 0})
        self.assertEqual(status, 200)
        self.assertEqual(self.db.get_inspiration("herfst|2")["ideas"][0]["recipe"]["image"], result["image"])
        self.assertTrue(self.db.image_in_use(result["image"]))
        self.assertEqual(self.call("POST", "/api/inspiration/photo", {"theme": "Herfst", "servings": 2, "index": 5})[0], 404)


if __name__ == "__main__":
    unittest.main()
