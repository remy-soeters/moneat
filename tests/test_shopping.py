import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.helpers import ApiClient, api_test
from mealplanner import ai
from mealplanner.db import Database, NotFound
from mealplanner.icons import IconMaker
from mealplanner.images import ImageStore
from mealplanner.routes.shopping import STAPLES
from tests.test_import import tiny_png

WEEK = "2026-09-21"


class ShoppingDbTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_manual_items_and_checking(self):
        milk = self.db.add_shopping_item("Melk", 1, "l")
        self.assertEqual(self.db.add_shopping_item("melk", 1, "l"), milk)  # samengevoegd
        items = self.db.shopping_list()
        self.assertEqual([(i["key"], i["name"], i["quantity"], i["manual"]) for i in items], [("buy:melk", "Melk", 2, True)])

        self.db.set_shopping_check("buy:melk", True)
        self.assertEqual([(i["key"], i["checked"]) for i in self.db.shopping_list()], [("bought:melk", True)])
        self.assertEqual(self.db.clear_bought_items(), 1)
        self.assertEqual(self.db.shopping_list(), [])

    def test_same_product_from_recipe_and_by_hand_is_one_tile(self):
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "Ui", "quantity": 2, "unit": ""}]})
        self.db.choose_dinner(WEEK, soup["id"])
        self.db.put_dinners_on_list([WEEK])
        self.db.add_shopping_item("ui", 1)
        (item,) = self.db.shopping_list()
        self.assertEqual((item["key"], item["quantity"], item["recipes"], item["manual"]), ("buy:ui", 3, ["Soep"], True))
        self.db.remove_shopping_item("buy:ui")
        self.assertEqual(self.db.shopping_list(), [])
        with self.assertRaises(NotFound):
            self.db.remove_shopping_item("buy:ui")

    def test_bought_items_become_frequent(self):
        recipe = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner(WEEK, recipe["id"])
        self.db.put_dinners_on_list([WEEK])
        self.db.set_shopping_check("buy:ui", True)
        self.db.set_shopping_check("bought:ui", True)  # al gekocht: telt niet nog eens
        self.db.set_shopping_check("bought:ui", False)
        self.db.set_shopping_check("buy:ui", True)
        self.db.add_shopping_item("Brood")
        self.db.set_shopping_check(next(i["key"] for i in self.db.shopping_list() if i["name"] == "Brood"), True)
        counts = {f["name"]: f["count"] for f in self.db.frequent_purchases()}
        self.assertEqual(counts, {"Ui": 1, "Brood": 1})

    def items(self):
        return {i["name"]: i for i in self.db.shopping_list()}

    def test_same_product_in_shop_units(self):
        """Blikken in plaats van grammen, hele stuks, en geen eetlepels op de lijst."""
        chili = self.db.create_recipe({"name": "Chili", "servings": 2, "ingredients": [
            {"name": "tomatenblokjes uit blik", "quantity": 400, "unit": "g"},
            {"name": "kidneybonen (blik)", "quantity": 240, "unit": "g"},
            {"name": "rode ui, gesnipperd", "quantity": 0.5, "unit": "stuks"},
            {"name": "olijfolie", "quantity": 2, "unit": "el"},
        ]})
        self.db.choose_dinner(WEEK, chili["id"])
        self.db.put_dinners_on_list([WEEK])
        self.db.add_shopping_item("tomatenblokjes", 1, "blik")
        self.db.add_shopping_item("rode uien", 1)
        items = self.items()
        self.assertEqual(items["Tomatenblokjes"]["amount"], "2 blikken")
        self.assertEqual(items["Kidneybonen"]["amount"], "1 blik")
        self.assertEqual(items["Rode ui"]["amount"], "2")  # een halve en een hele: twee kopen
        self.assertEqual(items["Olijfolie"]["amount"], "")
        self.assertEqual(len(items), 4)

    def test_fresh_and_canned_stay_apart(self):
        self.db.add_shopping_item("tomaten", 3)
        self.db.add_shopping_item("tomaten uit blik", 400, "g")
        items = self.items()
        self.assertEqual((items["Tomaten"]["amount"], items["Tomaten (blik)"]["amount"]), ("3", "1 blik"))

    def test_homemade_parts_are_replaced_by_their_ingredients(self):
        """Staat naan in je receptenboek, dan komen de ingrediënten daarvan op de lijst in plaats van naan."""
        self.db.create_recipe({"name": "Zelfgemaakte naan", "servings": 4, "ingredients": [
            {"name": "bloem", "quantity": 400, "unit": "g"}, {"name": "yoghurt", "quantity": 200, "unit": "ml"}]})
        curry = self.db.create_recipe({"name": "Curry", "servings": 2, "ingredients": [
            {"name": "naanbrood", "quantity": 2, "unit": "stuks"}, {"name": "kip", "quantity": 300, "unit": "g"}]})
        self.db.choose_dinner(WEEK, curry["id"], servings=2)
        self.db.put_dinners_on_list([WEEK])
        items = self.items()
        self.assertNotIn("Naanbrood", items)
        self.assertEqual((items["Bloem"]["amount"], items["Yoghurt"]["amount"]), ("200 g", "100 ml"))
        self.assertEqual(items["Bloem"]["recipes"], ["Zelfgemaakte naan"])

        result = self.db.add_ingredients_to_list([{"name": "naan", "quantity": 1, "unit": ""}], servings=4)
        self.assertEqual(result, {"added": 2, "homemade": ["Zelfgemaakte naan"]})

    def test_edit_an_item(self):
        self.db.add_shopping_item("tomatenblokjes uit blik", 400, "g")
        self.db.add_shopping_item("tomatenblokjes", 1, "blik")
        (item,) = self.db.shopping_list()
        self.assertEqual((item["quantity"], item["unit"]), (2, "blik"))
        self.db.update_shopping_item(item["key"], "Tomatenblokjes met basilicum", 3, "blik")
        (item,) = self.db.shopping_list()
        self.assertEqual((item["name"], item["amount"], item["manual"]), ("Tomatenblokjes met basilicum", "3 blikken", True))
        with self.assertRaises(ValueError):
            self.db.update_shopping_item(item["key"], "", 1, "")
        with self.assertRaises(ValueError):
            self.db.update_shopping_item(item["key"], "Tomaten", "veel", "")

    def test_suggestions_follow_your_rhythm(self):
        """Wat je elke week koopt en alweer een week geleden kocht, staat bovenaan."""
        with self.db.connect() as conn:
            for name, count, days in (("Melk", 3, 8), ("Koffie", 5, 1), ("Taart", 1, 90)):
                key = name.lower()
                conn.execute(
                    "INSERT INTO purchase_counts (key, name, count, last_at) VALUES (?, ?, ?, datetime('now', ?))",
                    (key, name, count, f"-{days} days"),
                )
                for i in range(count):
                    conn.execute(
                        "INSERT INTO purchase_log (key, bought_at) VALUES (?, datetime('now', ?))", (key, f"-{days + 7 * i} days")
                    )
        found = self.db.frequent_purchases()
        self.assertEqual([f["name"] for f in found], ["Melk", "Koffie", "Taart"])
        self.assertEqual([f["due"] for f in found], [True, False, False])

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

    def test_leaves_products_that_keep_their_emoji(self):
        self.db.set_product_icon("Zout", "")
        self.maker.request(["Zout"])
        self.wait()
        ai.generate_icon.assert_not_called()

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
        self.api = api_test(self, db=self.db, images=self.images)
        self.base = self.api.base

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def test_change_a_product_icon(self):
        """Een nieuw icoon laten tekenen (met een beschrijving), een eigen afbeelding kiezen of terug naar de emoji."""
        self.db.add_shopping_item("Olijfolie")
        with mock.patch.object(ai, "generate_icon", return_value=tiny_png()) as draw:
            status, res = self.call("POST", "/api/shopping/icon", {"name": "Olijfolie", "hint": "een fles"})
        self.assertEqual(status, 200)
        draw.assert_called_once_with("Olijfolie", "een fles")
        drawn = res["icon"]
        self.assertEqual(res["items"][0]["icon"], drawn)

        own = self.images.save(tiny_png())
        res = self.call("PUT", "/api/shopping/icon", {"name": "olijfolie", "image": own})[1]
        self.assertEqual(res["items"][0]["icon"], own)
        self.assertIsNone(self.images.path_for(drawn))  # het vorige icoon is opgeruimd

        res = self.call("PUT", "/api/shopping/icon", {"name": "Olijfolie", "image": ""})[1]
        self.assertEqual(res["items"][0]["icon"], "")
        self.assertEqual(self.db.product_icons(["Olijfolie"]), {"Olijfolie": ""})  # de app tekent er geen meer voor
        self.assertEqual(self.call("PUT", "/api/shopping/icon", {"name": "Olijfolie", "image": "/images/weg.png"})[0], 400)
        self.assertEqual(self.call("POST", "/api/shopping/icon", {"name": " "})[0], 400)

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
        self.assertEqual((item["name"], item["quantity"], item["unit"], item["icon"]), ("Melk", 2, "l", "/images/" + "b" * 32 + ".png"))
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
