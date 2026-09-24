import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from mealplanner import ai
from mealplanner.db import Database, NotFound
from mealplanner.icons import IconMaker
from mealplanner.images import ImageStore
from mealplanner.server import STAPLES, make_handler
from tests.test_import import tiny_png

WEEK = "2026-09-21"


class ShoppingDbTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_manual_items_and_checking(self):
        milk = self.db.add_shopping_item("Melk", 1, "l")
        self.assertEqual(self.db.add_shopping_item("melk", 1, "l"), milk)  # samengevoegd
        items = self.db.shopping_list()
        self.assertEqual([(i["key"], i["name"], i["quantity"], i["manual"]) for i in items], [("buy:melk|l", "Melk", 2, True)])

        self.db.set_shopping_check("buy:melk|l", True)
        self.assertEqual([(i["key"], i["checked"]) for i in self.db.shopping_list()], [("bought:melk|l", True)])
        self.assertEqual(self.db.clear_bought_items(), 1)
        self.assertEqual(self.db.shopping_list(), [])

    def test_same_product_from_recipe_and_by_hand_is_one_tile(self):
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "Ui", "quantity": 2, "unit": ""}]})
        self.db.choose_dinner(WEEK, soup["id"])
        self.db.add_shopping_item("ui", 1)
        (item,) = self.db.shopping_list()
        self.assertEqual((item["key"], item["quantity"], item["recipes"], item["manual"]), ("buy:ui|", 3, ["Soep"], True))
        self.db.remove_shopping_item("buy:ui|")
        self.assertEqual(self.db.shopping_list(), [])
        with self.assertRaises(NotFound):
            self.db.remove_shopping_item("buy:ui|")

    def test_bought_items_become_frequent(self):
        recipe = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner(WEEK, recipe["id"])
        self.db.set_shopping_check("buy:ui|", True)
        self.db.set_shopping_check("bought:ui|", True)  # al gekocht: telt niet nog eens
        self.db.set_shopping_check("bought:ui|", False)
        self.db.set_shopping_check("buy:ui|", True)
        self.db.add_shopping_item("Brood")
        self.db.set_shopping_check("buy:brood|", True)
        counts = {f["name"]: f["count"] for f in self.db.frequent_purchases()}
        self.assertEqual(counts, {"ui": 1, "Brood": 1})

    def test_icons_are_shared_per_product(self):
        self.db.set_product_icon("Rode ui ", "/images/" + "a" * 32 + ".png")
        self.assertEqual(self.db.product_icons(["rode  UI", "melk"]), {"rode  UI": "/images/" + "a" * 32 + ".png"})
        self.assertTrue(self.db.image_in_use("/images/" + "a" * 32 + ".png"))


class IconMakerTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        self.maker = IconMaker(self.db, self.images)
        for patch in (mock.patch.object(ai, "gemini_configured", return_value=True),
                      mock.patch.object(ai, "generate_icon", return_value=tiny_png())):
            patch.start()
            self.addCleanup(patch.stop)

    def wait(self):
        if self.maker.thread:
            self.maker.thread.join(timeout=10)

    def test_draws_each_product_once(self):
        self.maker.request(["Melk", "melk", "Brood"])
        self.wait()
        self.assertEqual(ai.generate_icon.call_count, 2)
        self.assertEqual(set(self.db.product_icons(["Melk", "Brood"])), {"Melk", "Brood"})
        self.maker.request(["Melk"])
        self.wait()
        self.assertEqual(ai.generate_icon.call_count, 2)
        self.assertFalse(self.maker.pending())

    def test_stops_after_failure(self):
        ai.generate_icon.side_effect = ai.AIUnavailable("betalen nodig")
        self.maker.request([f"Product {i}" for i in range(20)])
        self.wait()
        self.assertEqual(self.maker.failed, "betalen nodig")
        self.assertLessEqual(ai.generate_icon.call_count, 3)
        self.assertFalse(self.maker.enabled())


class ShoppingApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        # Geen echte iconen tekenen in deze tests.
        patch = mock.patch.object(ai, "gemini_configured", return_value=False)
        patch.start()
        self.addCleanup(patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db, self.images))
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

    def test_recipe_ingredients_go_on_the_list(self):
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "Ui", "quantity": 2, "unit": ""}]})
        self.db.add_shopping_item("ui", 1)
        status, result = self.call("POST", "/api/shopping/recipe", {
            "recipe_id": soup["id"],
            "ingredients": [{"name": "Ui", "quantity": 3, "unit": ""}, {"name": "zout", "quantity": None, "unit": ""},
                            {"name": " ", "quantity": 1, "unit": ""}],
        })
        self.assertEqual((status, result["added"]), (200, 2))
        items = {i["name"].lower(): i for i in result["items"]}
        self.assertEqual((items["ui"]["quantity"], items["ui"]["recipes"]), (4, ["Soep"]))
        self.assertIsNone(items["zout"]["quantity"])
        # Een idee dat (nog) geen recept is, kan ook; en een leeg recept geeft een nette melding.
        self.assertEqual(self.call("POST", "/api/shopping/recipe", {"ingredients": [{"name": "Prei", "quantity": 1, "unit": ""}]})[1]["added"], 1)
        self.assertEqual(self.call("POST", "/api/shopping/recipe", {"ingredients": []})[0], 400)
        self.db.delete_recipe(soup["id"])  # verwijderd recept: de niet-gekochte regels gaan mee
        self.assertEqual(sorted(i["name"].lower() for i in self.db.shopping_list()), ["prei", "ui"])

    def test_add_parses_quantity_and_returns_icons(self):
        self.db.set_product_icon("melk", "/images/" + "b" * 32 + ".png")
        status, result = self.call("POST", "/api/shopping/items", {"text": "2 liter melk"})
        self.assertEqual(status, 200)
        item = result["items"][0]
        self.assertEqual((item["name"], item["quantity"], item["unit"], item["icon"]), ("melk", 2, "l", "/images/" + "b" * 32 + ".png"))
        self.assertEqual(result["icons"]["enabled"], False)
        self.assertEqual(self.call("POST", "/api/shopping/items", {"text": "  "})[0], 400)

        self.call("POST", "/api/shopping/check", {"key": item["key"], "checked": True})
        self.assertEqual(self.call("POST", "/api/shopping/clear-bought", {})[1]["removed"], 1)
        key = self.call("POST", "/api/shopping/items", {"text": "brood"})[1]["items"][0]["key"]
        quoted = urllib.parse.quote(key)
        self.assertEqual(self.call("DELETE", f"/api/shopping/items?key={quoted}")[0], 200)
        self.assertEqual(self.call("DELETE", f"/api/shopping/items?key={quoted}")[0], 404)

    def test_suggestions_put_frequent_items_first(self):
        _, result = self.call("GET", "/api/shopping/suggestions")
        self.assertEqual(([s["name"] for s in result["suggestions"]][:3], result["has_history"]), (STAPLES[:3], False))
        item = self.call("POST", "/api/shopping/items", {"text": "Stroopwafels"})[1]["items"][0]
        self.call("POST", "/api/shopping/check", {"key": item["key"], "checked": True})
        _, result = self.call("GET", "/api/shopping/suggestions")
        self.assertEqual((result["suggestions"][0]["name"], result["has_history"]), ("Stroopwafels", True))


if __name__ == "__main__":
    unittest.main()
