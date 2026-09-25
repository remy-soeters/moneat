import json
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests.helpers import ApiClient, api_test
from mealplanner import ai
from mealplanner.db import Database
from mealplanner.images import ImageStore, sniff
from mealplanner.importer import (
    ImportFailed,
    find_recipe_json,
    import_recipe,
    parse_duration,
    parse_ingredient,
    parse_instructions,
    parse_page,
)


def tiny_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"\x00\xff\x00\x00"  # één rode pixel
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


RECIPE_PAGE = """<!doctype html><html><head>
<meta property="og:image" content="/fallback.png">
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "WebPage", "name": "Pompoensoep"},
  {"@type": "Recipe", "name": "Pompoensoep met gember",
   "image": ["/soep.png"], "recipeYield": "4 personen", "totalTime": "PT45M",
   "recipeCategory": "Soep", "keywords": "vegetarisch, herfst",
   "recipeIngredient": ["1 kg pompoen", "2 teentjes knoflook", "1½ el olijfolie", "snufje zout", "1 ui"],
   "recipeInstructions": [
     {"@type": "HowToSection", "name": "Soep", "itemListElement": [
       {"@type": "HowToStep", "text": "Snijd de pompoen in blokjes."},
       {"@type": "HowToStep", "text": "Kook 20 minuten en pureer."}]}]}
]}
</script></head><body><h1>Pompoensoep</h1></body></html>"""

PLAIN_PAGE = "<html><head><title>Oma's stoofvlees</title></head><body><p>Neem 500 g runderlappen…</p></body></html>"


class FakeSite(BaseHTTPRequestHandler):
    def do_GET(self):
        pages = {
            "/soep": ("text/html; charset=utf-8", RECIPE_PAGE.encode()),
            "/oma": ("text/html; charset=utf-8", PLAIN_PAGE.encode()),
            "/soep.png": ("image/png", tiny_png()),
        }
        if self.path not in pages:
            self.send_error(404)
            return
        content_type, body = pages[self.path]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ParsingTest(unittest.TestCase):
    def test_ingredients(self):
        self.assertEqual(parse_ingredient("200 g spaghetti"), {"name": "spaghetti", "quantity": 200, "unit": "g"})
        self.assertEqual(parse_ingredient("200g spaghetti"), {"name": "spaghetti", "quantity": 200, "unit": "g"})
        self.assertEqual(parse_ingredient("2 teentjes knoflook"), {"name": "knoflook", "quantity": 2, "unit": "teen"})
        self.assertEqual(parse_ingredient("1½ el olijfolie"), {"name": "olijfolie", "quantity": 1.5, "unit": "el"})
        self.assertEqual(parse_ingredient("1/2 tl paprikapoeder")["quantity"], 0.5)
        self.assertEqual(parse_ingredient("1 1/2 dl room"), {"name": "room", "quantity": 1.5, "unit": "dl"})
        self.assertEqual(parse_ingredient("2-3 tomaten"), {"name": "tomaten", "quantity": 2, "unit": ""})
        self.assertEqual(parse_ingredient("1 ui"), {"name": "ui", "quantity": 1, "unit": ""})
        self.assertEqual(parse_ingredient("snufje zout"), {"name": "snufje zout", "quantity": None, "unit": ""})
        self.assertEqual(parse_ingredient("1 g"), {"name": "g", "quantity": 1, "unit": ""})

    def test_tags_skip_noise(self):
        from mealplanner.importer import clean_tags

        data = {"recipeCategory": "Lunch recepten", "keywords": "soep, Cassie Best, herfstrecepten, soep",
                "author": {"name": "Cassie Best"}}
        self.assertEqual(clean_tags(data), ["lunch", "soep", "herfst"])

    def test_duration(self):
        self.assertEqual(parse_duration("PT45M"), 45)
        self.assertEqual(parse_duration("PT1H30M"), 90)
        self.assertIsNone(parse_duration(""))
        self.assertIsNone(parse_duration("P0D"))

    def test_instructions_strip_numbering(self):
        text = parse_instructions(["1. Snijd de ui.", {"text": "Stap 2: Fruit de ui."}, "Serveer.\nEet smakelijk."])
        self.assertEqual(text, "1. Snijd de ui.\n2. Fruit de ui.\n3. Serveer.\n4. Eet smakelijk.")

    def test_finds_recipe_in_graph(self):
        blocks, meta, _ = parse_page(RECIPE_PAGE)
        self.assertEqual(find_recipe_json(blocks)["name"], "Pompoensoep met gember")
        self.assertEqual(meta["og:image"], "/fallback.png")

    def test_sniff(self):
        self.assertEqual(sniff(tiny_png()), "png")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0rest"), "jpg")
        self.assertEqual(sniff(b"RIFF1234WEBPVP8 "), "webp")
        self.assertIsNone(sniff(b"<html>"))


class ImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
        cls.base = f"http://127.0.0.1:{cls.site.server_address[1]}"
        threading.Thread(target=cls.site.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.site.shutdown()
        cls.site.server_close()

    def setUp(self):
        self.images = ImageStore(tempfile.mkdtemp())

    def test_imports_schema_recipe_with_image(self):
        recipe = import_recipe(f"{self.base}/soep", self.images)
        self.assertEqual(recipe["name"], "Pompoensoep met gember")
        self.assertEqual((recipe["servings"], recipe["prep_minutes"]), (4, 45))
        self.assertEqual(recipe["tags"], "soep, vegetarisch, herfst")
        self.assertEqual(recipe["ingredients"][0], {"name": "pompoen", "quantity": 1, "unit": "kg"})
        self.assertEqual(recipe["instructions"], "1. Snijd de pompoen in blokjes.\n2. Kook 20 minuten en pureer.")
        self.assertEqual(recipe["source_url"], f"{self.base}/soep")
        self.assertTrue(self.images.path_for(recipe["image"]).read_bytes().startswith(b"\x89PNG"))

    def test_falls_back_to_claude_for_plain_pages(self):
        def fake_extract(text, url):
            self.assertIn("runderlappen", text)
            return {"name": "Stoofvlees", "servings": 4, "prep_minutes": 180, "tags": "", "instructions": "",
                    "ingredients": [{"name": "runderlappen", "quantity": 500, "unit": "g"}]}

        recipe = import_recipe(f"{self.base}/oma", self.images, ai_extract=fake_extract)
        self.assertEqual((recipe["name"], recipe["image"]), ("Stoofvlees", ""))

    def test_plain_page_without_ai_fails(self):
        with self.assertRaises(ImportFailed):
            import_recipe(f"{self.base}/oma", self.images)

    def test_rejects_other_schemes_and_missing_pages(self):
        with self.assertRaises(ImportFailed):
            import_recipe("file:///etc/passwd", self.images)
        with self.assertRaises(ImportFailed):
            import_recipe(f"{self.base}/bestaat-niet", self.images)


class RecipeBookApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        self.api = api_test(self, db=self.db, images=self.images)
        self.base = self.api.base

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def test_upload_image_and_clean_up_on_delete(self):
        status, result = self.call("POST", "/api/images", raw=tiny_png(), content_type="image/png")
        self.assertEqual(status, 200)
        image = result["image"]
        status, headers, _ = self.api.request("GET", image)
        self.assertEqual((status, headers["Content-Type"]), (200, "image/png"))
        anonymous = ApiClient(user=None, db=self.db, images=self.images)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.request("GET", image)[0], 401)  # niet ingelogd

        _, recipe = self.call("POST", "/api/recipes", {"name": "Soep", "image": image})
        self.assertEqual(recipe["image"], image)
        self.call("DELETE", f"/api/recipes/{recipe['id']}")
        self.assertIsNone(self.images.path_for(image))

    def test_replacing_image_removes_old_file(self):
        _, first = self.call("POST", "/api/images", raw=tiny_png(), content_type="image/png")
        _, second = self.call("POST", "/api/images", raw=tiny_png(), content_type="image/png")
        _, recipe = self.call("POST", "/api/recipes", {"name": "Soep", "image": first["image"]})
        self.call("PUT", f"/api/recipes/{recipe['id']}", {"name": "Soep", "image": second["image"]})
        self.assertIsNone(self.images.path_for(first["image"]))
        self.assertIsNotNone(self.images.path_for(second["image"]))

    def test_rejects_non_images_and_foreign_image_paths(self):
        self.assertEqual(self.call("POST", "/api/images", raw=b"<html>", content_type="image/png")[0], 400)
        self.assertEqual(self.call("POST", "/api/recipes", {"name": "X", "image": "/etc/passwd"})[0], 400)
        self.assertEqual(self.call("POST", "/api/recipes", {"name": "X", "source_url": "javascript:alert(1)"})[0], 400)

    def test_generate_recipe(self):
        draft = {"name": "Pompoenrisotto", "servings": 2, "prep_minutes": 40, "tags": "", "instructions": "",
                 "ingredients": []}
        with mock.patch.object(ai, "generate_recipe", return_value=draft) as fake:
            status, result = self.call("POST", "/api/recipes/generate", {"prompt": "risotto met pompoen", "servings": 3})
        self.assertEqual((status, result["name"]), (200, "Pompoenrisotto"))
        fake.assert_called_once_with("risotto met pompoen", 3)
        self.assertEqual(self.call("POST", "/api/recipes/generate", {"prompt": " "})[0], 400)

    def test_inspiration_is_cached_until_refresh(self):
        collection = {"intro": "Herfst!", "ideas": []}
        with mock.patch.object(ai, "inspiration", return_value=collection) as fake:
            self.call("POST", "/api/inspiration", {"theme": "Herfst", "servings": 2})
            status, result = self.call("POST", "/api/inspiration", {"theme": "herfst ", "servings": 2})
            self.assertEqual((status, result["intro"], fake.call_count), (200, "Herfst!", 1))
            self.call("POST", "/api/inspiration", {"theme": "Herfst", "servings": 2, "refresh": True})
            self.assertEqual(fake.call_count, 2)


if __name__ == "__main__":
    unittest.main()
