import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.helpers import ApiClient, api_test
from mealplanner import ai
from mealplanner.db import Database
from mealplanner.images import ImageStore
from tests.test_import import tiny_png


def idea(name, description="Heerlijk"):
    return {"description": description, "recipe": {
        "name": name, "servings": 2, "prep_minutes": 25, "tags": "test", "instructions": "1. Koken.",
        "ingredients": [{"name": "ui", "quantity": 1, "unit": "stuks"}],
    }}


class SwipeDbTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_like_saves_recipe_with_photo_and_skip_does_not(self):
        self.db.create_recipe({"name": "Pasta pesto"})
        added = self.db.add_swipe_cards([idea("Shakshuka"), idea("pasta pesto"), idea("Shakshuka"), idea("Dahl")])
        self.assertEqual(added, 2)  # bestaande en dubbele namen worden overgeslagen
        shakshuka, dahl = self.db.pending_swipe_cards()
        self.db.set_swipe_card_image(shakshuka["id"], "/images/" + "a" * 32 + ".png")

        recipe = self.db.swipe(shakshuka["id"], liked=True)
        self.assertEqual((recipe["name"], recipe["image"]), ("Shakshuka", "/images/" + "a" * 32 + ".png"))
        self.assertIsNone(self.db.swipe(dahl["id"], liked=False))

        self.assertEqual(sorted(r["name"] for r in self.db.list_recipes()), ["Pasta pesto", "Shakshuka"])
        self.assertEqual(self.db.pending_swipe_cards(), [])
        self.assertEqual(self.db.swipe_stats()["liked"], 1)
        self.assertEqual(self.db.swipe_stats()["skipped"], 1)
        with self.assertRaises(ValueError):
            self.db.swipe(dahl["id"], liked=True)  # al geswipet

    def test_undo_restores_card_and_removes_recipe(self):
        self.db.add_swipe_cards([idea("Shakshuka")])
        card = self.db.pending_swipe_cards()[0]
        self.db.swipe(card["id"], liked=True)
        restored = self.db.undo_swipe()
        self.assertEqual((restored["id"], restored["status"]), (card["id"], "pending"))
        self.assertEqual(self.db.list_recipes(), [])
        self.assertIsNone(self.db.undo_swipe())

    def test_seen_names_include_skipped_cards(self):
        self.db.add_swipe_cards([idea("Dahl")])
        self.db.swipe(self.db.pending_swipe_cards()[0]["id"], liked=False)
        self.assertIn("Dahl", self.db.known_dish_names())
        self.assertEqual(self.db.add_swipe_cards([idea("DAHL")]), 0)

    def test_clear_pending_keeps_swiped_cards(self):
        self.db.add_swipe_cards([idea("Dahl"), idea("Risotto")])
        dahl, risotto = self.db.pending_swipe_cards()
        self.db.set_swipe_card_image(risotto["id"], "/images/" + "c" * 32 + ".png")
        self.db.swipe(dahl["id"], liked=False)
        self.assertEqual(self.db.clear_pending_swipe_cards(), ["/images/" + "c" * 32 + ".png"])
        self.assertEqual(self.db.pending_swipe_cards(), [])
        self.assertIn("Dahl", self.db.known_dish_names())

    def test_card_image_counts_as_in_use(self):
        self.db.add_swipe_cards([idea("Dahl")])
        image = "/images/" + "b" * 32 + ".png"
        self.db.set_swipe_card_image(self.db.pending_swipe_cards()[0]["id"], image)
        self.assertTrue(self.db.image_in_use(image))


class SwipePromptTest(unittest.TestCase):
    def test_preferences_end_up_in_the_request(self):
        prefs = {"diet": "pescotarisch", "cuisines": ["Grieks"], "max_minutes": 20, "avoid": "noten"}
        with mock.patch.object(ai, "_ask", return_value={"ideas": [idea(f"Gerecht {i}") for i in range(10)]}) as fake:
            ideas = ai.swipe_recipes(prefs, count=4, exclude=["Dahl", "Risotto"], servings=3)
        self.assertEqual(len(ideas), 4)
        system, message, schema = fake.call_args.args
        for expected in ("4 avondgerechten voor 3 personen", "wel vis, geen vlees", "Grieks", "maximaal 20 minuten",
                         "noten", "Al gezien: Dahl, Risotto"):
            self.assertIn(expected, message)
        self.assertEqual(schema, ai.SWIPE_SCHEMA)


class SwipeApiTest(unittest.TestCase):
    def setUp(self):
        # Het klaarzetten op de achtergrond heeft eigen tests; hier mag het niet de echte AI aanroepen.
        kick = mock.patch("mealplanner.preloader.SwipePreloader.kick")
        kick.start()
        self.addCleanup(kick.stop)
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        self.api = api_test(self, db=self.db, images=self.images)
        self.base = self.api.base

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def test_preferences_are_validated_and_used(self):
        prefs = {"diet": "vegetarisch", "cuisines": ["Italiaans", "Indiaas"], "max_minutes": 30, "avoid": "koriander"}
        status, saved = self.call("PUT", "/api/preferences", prefs)
        self.assertEqual((status, saved), (200, prefs))
        self.assertEqual(self.call("GET", "/api/preferences")[1], prefs)
        self.assertEqual(self.call("PUT", "/api/preferences", {"diet": "carnivoor"})[0], 400)
        self.assertEqual(self.call("PUT", "/api/preferences", {"max_minutes": 17})[0], 400)

        self.db.create_recipe({"name": "Pasta pesto"})
        with mock.patch.object(ai, "swipe_recipes", return_value=[idea("Dahl"), idea("Risotto")]) as fake:
            status, result = self.call("POST", "/api/swipe/more", {"count": 2, "servings": 3})
        self.assertEqual((status, result["added"], len(result["cards"])), (200, 2, 2))
        called_prefs, count = fake.call_args.args
        self.assertEqual((called_prefs, count, fake.call_args.kwargs["servings"]), (prefs, 2, 3))
        self.assertIn("Pasta pesto", fake.call_args.kwargs["exclude"])

    def test_preload_setting_and_status(self):
        from mealplanner.preloader import SwipePreloader

        status, settings = self.call("GET", "/api/settings")
        self.assertEqual((settings["swipe_preload"], settings["swipe_preload_options"]), (10, [5, 10, 15, 20]))
        self.assertEqual(self.call("PUT", "/api/settings", {"swipe_preload": 15})[1]["swipe_preload"], 15)
        self.assertEqual(self.call("PUT", "/api/settings", {"swipe_preload": 7})[0], 400)

        status, result = self.call("POST", "/api/swipe/preload", {"servings": 4, "retry": True})
        self.assertEqual((status, result["target"]), (200, 15))
        SwipePreloader.kick.assert_called_with(4, retry=True)
        self.assertIn("preload", self.call("GET", "/api/swipe")[1])

    def test_swipe_flow_with_photo_and_undo(self):
        self.db.add_swipe_cards([idea("Dahl")])
        card = self.call("GET", "/api/swipe")[1]["cards"][0]
        with mock.patch.object(ai, "generate_photo", return_value=tiny_png()):
            _, first = self.call("POST", f"/api/swipe/cards/{card['id']}/photo")
            _, second = self.call("POST", f"/api/swipe/cards/{card['id']}/photo")
        self.assertIsNone(self.images.path_for(first["image"]))  # vervangen foto is opgeruimd

        status, result = self.call("POST", f"/api/swipe/cards/{card['id']}", {"liked": True})
        self.assertEqual((status, result["recipe"]["image"], result["stats"]["liked"]), (200, second["image"], 1))
        self.assertEqual(self.call("POST", f"/api/swipe/cards/{card['id']}", {"liked": True})[0], 400)

        status, result = self.call("POST", "/api/swipe/undo")
        self.assertEqual((status, result["card"]["status"]), (200, "pending"))
        self.assertEqual(self.db.list_recipes(), [])
        self.assertIsNotNone(self.images.path_for(second["image"]))  # de kaart gebruikt de foto nog


if __name__ == "__main__":
    unittest.main()
