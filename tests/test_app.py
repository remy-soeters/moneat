import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from mealplanner.db import Database, week_dates
from mealplanner.server import make_handler

PASTA = {
    "name": "Pasta pesto",
    "servings": 2,
    "prep_minutes": 20,
    "tags": "vegetarisch, pasta",
    "instructions": "1. Kook de pasta.\n2. Meng met pesto.",
    "ingredients": [
        {"name": "Pasta", "quantity": 200, "unit": "g"},
        {"name": "Pesto", "quantity": "1,5", "unit": "el"},
        {"name": "Basilicum", "quantity": None, "unit": ""},
    ],
}


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_week_dates_start_on_monday(self):
        self.assertEqual(week_dates("2026-09-24")[0], "2026-09-21")
        self.assertEqual(week_dates("2026-09-27")[-1], "2026-09-27")

    def test_recipe_roundtrip_parses_decimal_comma(self):
        recipe = self.db.create_recipe(PASTA)
        self.assertEqual(recipe["ingredients"][1]["quantity"], 1.5)
        self.assertIsNone(recipe["ingredients"][2]["quantity"])

    def test_recipe_requires_name(self):
        with self.assertRaises(ValueError):
            self.db.create_recipe({"name": "  "})

    def test_shopping_list_scales_and_sums(self):
        pasta = self.db.create_recipe(PASTA)
        other = self.db.create_recipe(
            {"name": "Pasta carbonara", "servings": 4, "ingredients": [{"name": "pasta", "quantity": 400, "unit": "G"}]}
        )
        self.db.choose_dinner("2026-09-21", pasta["id"], servings=4)  # 2x recept
        self.db.choose_dinner("2026-09-22", other["id"], servings=2)  # 0,5x recept
        self.db.choose_dinner("2026-09-28", pasta["id"])  # volgende week: telt niet mee
        self.db.add_menu_option("2026-09-23", pasta["id"])  # alleen een optie: telt niet mee

        items = {i["key"]: i for i in self.db.shopping_list("2026-09-24")}
        self.assertEqual(items["pasta|g"]["quantity"], 600)
        self.assertEqual(items["pasta|g"]["recipes"], ["Pasta carbonara", "Pasta pesto"])
        self.assertEqual(items["pesto|el"]["quantity"], 3)
        self.assertIsNone(items["basilicum|"]["quantity"])

    def test_shopping_checks_are_per_week(self):
        pasta = self.db.create_recipe(PASTA)
        self.db.choose_dinner("2026-09-21", pasta["id"])
        self.db.set_shopping_check("2026-09-23", "pasta|g", True)
        checked = {i["key"] for i in self.db.shopping_list("2026-09-21") if i["checked"]}
        self.assertEqual(checked, {"pasta|g"})
        self.db.set_shopping_check("2026-09-21", "pasta|g", False)
        self.assertFalse(any(i["checked"] for i in self.db.shopping_list("2026-09-21")))

    def test_menu_options_and_choice(self):
        pasta = self.db.create_recipe(PASTA)
        soup = self.db.create_recipe({"name": "Tomatensoep"})
        soup_option = self.db.add_menu_option("2026-09-21", soup["id"], "snel")
        pasta_option = self.db.add_menu_option("2026-09-21", pasta["id"])
        self.assertEqual(self.db.add_menu_option("2026-09-21", pasta["id"]), pasta_option)  # geen dubbele

        menu = self.db.get_week_menu("2026-09-24")
        self.assertEqual([o["name"] for o in menu["options"]], ["Tomatensoep", "Pasta pesto"])
        self.assertEqual(menu["options"][0]["reason"], "snel")
        self.assertEqual(menu["choices"], [])

        self.db.choose_option(pasta_option)
        self.db.choose_option(soup_option, servings=3)  # andere keuze vervangt de vorige
        choices = self.db.get_week_menu("2026-09-21")["choices"]
        self.assertEqual([(c["recipe_name"], c["servings"]) for c in choices], [("Tomatensoep", 3)])

        self.db.clear_dinner_choice("2026-09-21")
        self.assertEqual(self.db.get_week_menu("2026-09-21")["choices"], [])

    def test_suggestion_is_saved_as_recipe_only_when_chosen(self):
        option_id = self.db.add_suggested_option("2026-09-22", {**PASTA, "name": "Risotto"}, "romig")
        self.assertIsNone(self.db.add_suggested_option("2026-09-22", {"name": "risotto"}))  # zelfde naam
        self.assertEqual(self.db.list_recipes(), [])

        option = self.db.get_week_menu("2026-09-22")["options"][0]
        self.assertEqual((option["name"], option["saved"], option["source"]), ("Risotto", False, "claude"))
        self.assertEqual(len(option["suggestion"]["ingredients"]), 3)

        self.db.choose_option(option_id, servings=4)
        self.assertEqual([r["name"] for r in self.db.list_recipes()], ["Risotto"])
        menu = self.db.get_week_menu("2026-09-22")
        self.assertTrue(menu["options"][0]["saved"])
        self.assertEqual(menu["choices"][0]["recipe_name"], "Risotto")
        self.assertEqual({i["key"]: i["quantity"] for i in self.db.shopping_list("2026-09-22")}["pasta|g"], 400)

    def test_removing_suggestion_leaves_no_recipe(self):
        option_id = self.db.add_suggested_option("2026-09-22", {"name": "Risotto"})
        self.db.remove_menu_option(option_id)
        self.assertEqual(self.db.get_week_menu("2026-09-22")["options"], [])
        self.assertEqual(self.db.list_recipes(), [])

    def test_choosing_unlisted_recipe_adds_it_to_menu(self):
        pasta = self.db.create_recipe(PASTA)
        self.db.choose_dinner("2026-09-22", pasta["id"])
        self.assertEqual([o["recipe_id"] for o in self.db.get_week_menu("2026-09-22")["options"]], [pasta["id"]])

    def test_removing_chosen_option_clears_choice(self):
        pasta = self.db.create_recipe(PASTA)
        option_id = self.db.add_menu_option("2026-09-22", pasta["id"])
        self.db.choose_option(option_id)
        self.db.remove_menu_option(option_id)
        menu = self.db.get_week_menu("2026-09-22")
        self.assertEqual((menu["options"], menu["choices"]), ([], []))

    def test_copy_previous_week_copies_options_not_choices(self):
        pasta = self.db.create_recipe(PASTA)
        self.db.add_suggested_option("2026-09-15", {"name": "Tomatensoep"})  # dinsdag vorige week
        self.db.choose_dinner("2026-09-15", pasta["id"])
        self.assertEqual(self.db.copy_menu_from_previous_week("2026-09-24"), 2)
        menu = self.db.get_week_menu("2026-09-24")
        self.assertEqual({(o["date"], o["name"]) for o in menu["options"]},
                         {("2026-09-22", "Tomatensoep"), ("2026-09-22", "Pasta pesto")})
        self.assertEqual(menu["choices"], [])

    def test_deleting_recipe_clears_menu(self):
        pasta = self.db.create_recipe(PASTA)
        self.db.choose_dinner("2026-09-21", pasta["id"])
        self.db.delete_recipe(pasta["id"])
        menu = self.db.get_week_menu("2026-09-21")
        self.assertEqual((menu["options"], menu["choices"]), ([], []))

    def test_migrates_old_dinner_entries(self):
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE recipes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, servings INTEGER NOT NULL DEFAULT 2,
                    prep_minutes INTEGER, instructions TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '');
                CREATE TABLE plan_entries (id INTEGER PRIMARY KEY, date TEXT, slot TEXT, recipe_id INTEGER, servings INTEGER);
                INSERT INTO recipes (id, name) VALUES (1, 'Pasta'), (2, 'Havermout');
                INSERT INTO plan_entries (date, slot, recipe_id, servings) VALUES
                    ('2026-09-21', 'diner', 1, 3), ('2026-09-21', 'ontbijt', 2, 1);
            """)
            conn.commit()
            conn.close()

            menu = Database(path).get_week_menu("2026-09-21")
            self.assertEqual([(c["recipe_name"], c["servings"]) for c in menu["choices"]], [("Pasta", 3)])
            self.assertEqual([o["name"] for o in menu["options"]], ["Pasta"])

    def test_migrates_first_menu_options_table(self):
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v1.db"
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE recipes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, servings INTEGER NOT NULL DEFAULT 2,
                    prep_minutes INTEGER, instructions TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '');
                CREATE TABLE menu_options (date TEXT NOT NULL, recipe_id INTEGER NOT NULL, position INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '', PRIMARY KEY (date, recipe_id));
                INSERT INTO recipes (id, name) VALUES (1, 'Pasta');
                INSERT INTO menu_options (date, recipe_id, reason) VALUES ('2026-09-21', 1, 'lekker');
            """)
            conn.commit()
            conn.close()

            options = Database(path).get_week_menu("2026-09-21")["options"]
            self.assertEqual([(o["name"], o["reason"], o["saved"]) for o in options], [("Pasta", "lekker", True)])


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Database(":memory:")))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_full_flow(self):
        status, recipe = self.call("POST", "/api/recipes", PASTA)
        self.assertEqual(status, 200)
        status, option = self.call("POST", "/api/menu/options", {"date": "2026-09-23", "recipe_id": recipe["id"]})
        self.assertEqual(status, 200)
        status, _ = self.call("POST", f"/api/menu/options/{option['id']}/choose", {"servings": 4})
        self.assertEqual(status, 200)
        status, menu = self.call("GET", "/api/menu?week=2026-09-23")
        self.assertEqual(menu["days"][0], "2026-09-21")
        self.assertEqual(menu["choices"][0]["recipe_name"], "Pasta pesto")
        status, items = self.call("GET", "/api/shopping?week=2026-09-23")
        self.assertEqual({i["key"]: i["quantity"] for i in items}["pasta|g"], 400)

        self.assertEqual(self.call("DELETE", "/api/menu/choice?date=2026-09-23")[0], 200)
        self.assertEqual(self.call("DELETE", f"/api/menu/options/{option['id']}")[0], 200)
        status, menu = self.call("GET", "/api/menu?week=2026-09-23")
        self.assertEqual((menu["options"], menu["choices"]), ([], []))

    def test_fill_menu_tops_up_to_three_per_evening(self):
        from datetime import date, timedelta
        from unittest import mock

        from mealplanner import ai

        # Een week die helemaal in de toekomst ligt.
        monday = date.today() + timedelta(days=7 - date.today().weekday() + 7)
        mon, tue, wed = (str(monday + timedelta(days=i)) for i in range(3))
        _, recipe = self.call("POST", "/api/recipes", {**PASTA, "name": "Vul-pasta"})
        self.call("POST", "/api/menu/options", {"date": mon, "recipe_id": recipe["id"]})  # maandag: al 1
        _, option = self.call("POST", "/api/menu/options", {"date": tue, "recipe_id": recipe["id"]})
        self.call("POST", f"/api/menu/options/{option['id']}/choose", {})  # dinsdag: al gekozen

        def fake(recipes, needs, **kwargs):
            fake.needs = needs
            return [
                {"date": day, "existing_recipe_id": None, "new_recipe": {"name": f"Gerecht {day} {i}"}, "reason": "test"}
                for day, count in needs.items()
                for i in range(count)
            ]

        with mock.patch.object(ai, "suggest_menu_options", side_effect=fake):
            status, result = self.call("POST", "/api/menu/fill", {"week": mon})
        self.assertEqual(status, 200)
        self.assertEqual(fake.needs[mon], 2)
        self.assertNotIn(tue, fake.needs)
        self.assertEqual(fake.needs[wed], 3)
        self.assertEqual(result["added"], 2 + 5 * 3)

    def test_fill_menu_skips_past_evenings(self):
        from datetime import date, timedelta
        from unittest import mock

        from mealplanner import ai

        last_week = date.today() - timedelta(days=7)
        with mock.patch.object(ai, "suggest_menu_options") as fake:
            status, result = self.call("POST", "/api/menu/fill", {"week": str(last_week)})
        self.assertEqual((status, result["added"]), (200, 0))
        fake.assert_not_called()

    def test_errors_are_json(self):
        self.assertEqual(self.call("GET", "/api/recipes/9999")[0], 404)
        self.assertEqual(self.call("GET", "/api/menu")[0], 400)
        self.assertEqual(self.call("POST", "/api/menu/options", {"date": "2026-09-23", "recipe_id": 9999})[0], 404)
        self.assertEqual(self.call("POST", "/api/menu/options/9999/choose", {})[0], 404)
        self.assertEqual(self.call("POST", "/api/recipes", {"name": ""})[0], 400)

    def test_serves_frontend(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn(b"Mealplanner", res.read())
        with urllib.request.urlopen(self.base + "/../mealplanner/db.py") as res:
            self.assertNotIn(b"sqlite3", res.read())


if __name__ == "__main__":
    unittest.main()
