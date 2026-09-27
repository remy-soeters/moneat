"""Schetsen van de AI volledig laten uitschrijven: op de achtergrond, en als je er zelf om vraagt."""

import json
import unittest
from datetime import date, timedelta
from unittest import mock

from mealplanner import ai
from mealplanner.db import Database
from mealplanner.db.cleaning import clean_recipe
from mealplanner.writer import RecipeWriter
from tests.helpers import api_test

DAY = (date.today() + timedelta(days=1)).isoformat()
PHOTO = "/images/" + "a" * 32 + ".jpg"
SKETCH = {"name": "Soep", "servings": 2, "instructions": "1. Koken.", "draft": True,
          "ingredients": [{"name": "prei", "quantity": 2, "unit": ""}]}


def written(**extra):
    return {"name": "Andere naam", "servings": 4, "prep_minutes": 45, "tags": "soep, winter",
            "instructions": "1. Snijd de prei.\n2. Fruit de prei.\n3. Voeg de bouillon toe.",
            "ingredients": [{"name": "prei", "quantity": 2, "unit": ""}, {"name": "bouillonblokje", "quantity": 1, "unit": ""}],
            **extra}


class RecipeWriterTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.errors = []
        self.writer = RecipeWriter(self.db, lambda *args: self.errors.append(args))

    def run_writer(self, **kwargs):
        self.writer.kick(**kwargs)
        if self.writer.thread:
            self.writer.thread.join(5)

    def test_write_keeps_name_servings_and_photo(self):
        recipe = self.db.create_recipe({**SKETCH, "image": PHOTO})
        self.assertEqual((recipe["draft"], self.db.draft_recipe_ids()), (True, [recipe["id"]]))
        with mock.patch.object(ai, "write_out_recipe", return_value=written()) as write:
            result = self.writer.write(recipe["id"])
        self.assertEqual(write.call_args.args[0]["instructions"], "1. Koken.")
        self.assertEqual((result["name"], result["servings"], result["image"], result["draft"]), ("Soep", 2, PHOTO, False))
        self.assertEqual((result["prep_minutes"], result["tags"], len(result["ingredients"])), (45, "soep, winter", 2))
        self.assertEqual(self.db.draft_recipe_ids(), [])

    def test_own_changes_in_the_meantime_are_kept(self):
        recipe = self.db.create_recipe(SKETCH)

        def edit_while_writing(before):
            self.db.update_recipe(recipe["id"], {**before, "instructions": "Mijn eigen versie"})
            return written()

        with mock.patch.object(ai, "write_out_recipe", side_effect=edit_while_writing):
            self.assertIsNone(self.writer.write(recipe["id"]))
        self.assertEqual(self.db.get_recipe(recipe["id"])["instructions"], "Mijn eigen versie")
        with mock.patch.object(ai, "write_out_recipe", return_value=written()):  # zelf gevraagd: dan wel
            self.assertTrue(self.writer.write(recipe["id"], force=True)["instructions"].startswith("1. Snijd"))

    def test_background_writes_every_sketch_and_updates_the_list(self):
        soup = self.db.create_recipe(SKETCH)
        self.db.create_recipe({**SKETCH, "name": "Stoof"})
        self.db.create_recipe({**SKETCH, "name": "Eigen recept", "draft": False})
        self.db.choose_dinner(DAY, soup["id"])
        self.db.put_dinners_on_list([DAY])
        with mock.patch.object(ai, "write_out_recipe", return_value=written()) as write:
            self.run_writer()
        self.assertEqual((write.call_count, self.db.draft_recipe_ids()), (2, []))
        self.assertEqual(sorted(i["name"].lower() for i in self.db.shopping_list()), ["bouillonblokje", "prei"])

    def test_failure_is_logged_and_tried_again_later(self):
        self.db.create_recipe(SKETCH)
        with mock.patch.object(ai, "write_out_recipe", side_effect=ai.AIUnavailable("Limiet bereikt", "HTTP 429", "Gemini")) as write:
            self.run_writer()
            self.run_writer()  # meteen daarna: nog niet opnieuw
        self.assertEqual(write.call_count, 1)
        self.assertEqual(self.errors, [("Gemini", "Recepten uitschrijven", "Limiet bereikt", "HTTP 429")])
        with mock.patch.object(ai, "write_out_recipe", return_value=written()):
            self.run_writer(retry=True)
        self.assertEqual(self.db.draft_recipe_ids(), [])


class BatchesAreSketchesTest(unittest.TestCase):
    """Wat met vele tegelijk bedacht wordt, is een schets; één recept laten bedenken niet."""

    def test_menu_options_swipe_and_inspiration_are_marked(self):
        new = {"date": DAY, "existing_recipe_id": None, "new_recipe": written(name="Curry"), "reason": "lekker"}
        with mock.patch.object(ai, "_ask", return_value={"suggestions": [new]}):
            self.assertTrue(ai.suggest_menu_options([], {DAY: 1}, [])[0]["new_recipe"]["draft"])
        ideas = {"intro": "", "ideas": [{"description": "", "recipe": written()}]}
        with mock.patch.object(ai, "_ask", return_value=ideas):
            self.assertTrue(ai.inspiration("herfst")["ideas"][0]["recipe"]["draft"])
            self.assertTrue(ai.swipe_recipes({}, 1)[0]["recipe"]["draft"])
        with mock.patch.object(ai, "_ask", return_value=written()) as ask:
            self.assertNotIn("draft", ai.generate_recipe("iets met prei", 3, dinner=True))
        self.assertIn("volledig uit", ask.call_args.args[0])  # de uitgebreide regels
        self.assertIn("iets met prei", ask.call_args.args[1])

    def test_empty_write_out_is_an_error(self):
        with mock.patch.object(ai, "_ask", return_value=written(ingredients=[])):
            with self.assertRaises(ai.AIUnavailable):
                ai.write_out_recipe(SKETCH)


class OlderSuggestionsTest(unittest.TestCase):
    """Kaarten, inspiratie en opties van vóór het uitschrijven (zonder `draft`) worden ook uitgeschreven."""

    def setUp(self):
        self.db = Database(":memory:")
        self.old = {k: v for k, v in clean_recipe(SKETCH).items() if k != "draft"}  # zoals ze toen bewaard werden

    def store_old(self, table, column, **values):
        with self.db.connect() as conn:
            columns = [column, *values]
            conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                         [json.dumps(self.old), *values.values()])
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_old_swipe_card_menu_option_and_inspiration(self):
        card = self.store_old("swipe_cards", "recipe")
        self.assertTrue(self.db.swipe(card, True)["draft"])
        option = self.store_old("menu_options", "suggestion", date=DAY, source="claude")
        self.assertTrue(self.db.get_recipe(self.db.save_option_recipe(option))["draft"])
        with self.db.connect() as conn:
            conn.execute("INSERT INTO inspiration (key, created_at, payload) VALUES ('herfst|2', '2026-09-01', ?)",
                         ['{"intro": "", "ideas": [{"description": "", "recipe": {"name": "Soep"}}]}'])
        self.assertTrue(self.db.get_inspiration("herfst|2")["ideas"][0]["recipe"]["draft"])
        # Wat je zelf omschreef, is al volledig: dat blijft zo.
        described = self.db.add_suggested_option(DAY, {**SKETCH, "name": "Curry", "draft": False})
        self.assertFalse(self.db.get_option(described)["suggestion"]["draft"])


class WriteApiTest(unittest.TestCase):
    def setUp(self):
        self.api = api_test(self)
        self.db = self.api.db

    def test_choosing_a_sketch_writes_it_out(self):
        option = self.db.add_suggested_option(DAY, SKETCH, "lekker")
        self.assertTrue(self.db.get_option(option)["suggestion"]["draft"])
        with mock.patch.object(ai, "write_out_recipe", return_value=written()):
            self.assertEqual(self.api.call("POST", f"/api/menu/options/{option}/choose", {"servings": 2})[0], 200)
            self.api.app.writer.thread.join(5)
        recipe = self.db.get_recipe(self.db.get_option(option)["recipe_id"])
        self.assertEqual((recipe["name"], recipe["draft"], len(recipe["ingredients"])), ("Soep", False, 2))

    def test_status_and_write_on_request(self):
        recipe = self.db.create_recipe({**SKETCH, "draft": False})
        status, body = self.api.call("GET", f"/api/recipes/{recipe['id']}")
        self.assertEqual((status, body["draft"], "writing" in body), (200, False, False))
        with mock.patch.object(ai, "write_out_recipe", return_value=written()) as write:
            status, body = self.api.call("POST", f"/api/recipes/{recipe['id']}/write")
        self.assertEqual((status, body["name"], body["draft"], body["prep_minutes"]), (200, "Soep", False, 45))
        self.assertEqual(write.call_count, 1)
        with mock.patch.object(ai, "write_out_recipe", side_effect=ai.AIUnavailable("Geen sleutel")):
            self.assertEqual(self.api.call("POST", f"/api/recipes/{recipe['id']}/write")[0], 503)
        self.assertEqual(self.api.call("POST", "/api/recipes/999/write")[0], 404)


if __name__ == "__main__":
    unittest.main()
