import json
import threading
import re
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests.helpers import ApiClient, api_test
from mealplanner.db import Database, week_dates

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

    def test_shopping_list_scales_and_sums_across_weeks(self):
        pasta = self.db.create_recipe(PASTA)
        other = self.db.create_recipe(
            {"name": "Pasta carbonara", "servings": 4, "ingredients": [{"name": "pasta", "quantity": 400, "unit": "G"}]}
        )
        self.db.choose_dinner("2026-09-21", pasta["id"], servings=4)  # 2x recept
        self.db.choose_dinner("2026-09-22", other["id"], servings=2)  # 0,5x recept
        self.db.choose_dinner("2026-09-28", pasta["id"])  # volgende week: staat ook op de ene lijst
        self.db.add_menu_option("2026-09-23", pasta["id"])  # alleen een optie: telt niet mee
        added = self.db.put_dinners_on_list(["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-28"])
        self.assertEqual(added, ["2026-09-21", "2026-09-22", "2026-09-28"])

        items = {i["key"]: i for i in self.db.shopping_list()}
        self.assertEqual(items["buy:pasta"]["quantity"], 400 + 200 + 200)
        self.assertEqual(set(items["buy:pasta"]["recipes"]), {"Pasta carbonara", "Pasta pesto"})
        self.assertEqual(items["buy:pasta"]["amount"], "800 g")
        self.assertEqual(items["buy:pesto"]["amount"], "")  # eetlepels koop je niet: alleen het product
        self.assertIsNone(items["buy:basilicum"]["quantity"])

    def test_list_follows_dinner_choices(self):
        pasta = self.db.create_recipe(PASTA)
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner("2026-09-21", pasta["id"])
        self.db.put_dinners_on_list(["2026-09-21"])
        self.db.set_shopping_check("buy:pasta", True)  # pasta al gekocht

        self.db.choose_dinner("2026-09-21", pasta["id"], servings=4)  # meer personen: de lijst verandert mee
        items = {i["key"]: i for i in self.db.shopping_list()}
        self.assertIn("buy:pesto", items)  # opnieuw berekend
        self.assertEqual(items["bought:pasta"]["quantity"], 200)  # gekocht blijft staan...
        self.assertNotIn("buy:pasta", items)  # ...en komt niet nog eens op de lijst

        self.db.choose_dinner("2026-09-21", soup["id"])  # andere keuze
        self.assertEqual({i["key"] for i in self.db.shopping_list()}, {"bought:pasta", "buy:ui"})
        self.db.clear_dinner_choice("2026-09-21")
        self.assertEqual({i["key"] for i in self.db.shopping_list()}, {"bought:pasta"})
        self.db.choose_dinner("2026-09-21", soup["id"])  # de avond staat nog op de lijst: die volgt weer
        self.assertEqual({i["key"] for i in self.db.shopping_list()}, {"bought:pasta", "buy:ui"})

    def test_choosing_leaves_the_list_alone_until_you_put_it_on(self):
        pasta = self.db.create_recipe(PASTA)
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner("2026-09-21", pasta["id"])
        self.db.choose_dinner("2026-09-22", soup["id"])
        self.assertEqual(self.db.shopping_list(), [])
        self.assertEqual([c["listed"] for c in self.db.get_week_menu("2026-09-21")["choices"]], [False, False])

        self.assertEqual(self.db.put_dinners_on_list(["2026-09-21"]), ["2026-09-21"])
        self.assertEqual({i["key"] for i in self.db.shopping_list()}, {"buy:pasta", "buy:pesto", "buy:basilicum"})
        listed = {c["date"]: c["listed"] for c in self.db.get_week_menu("2026-09-21")["choices"]}
        self.assertEqual(listed, {"2026-09-21": True, "2026-09-22": False})

        # Wat je van de lijst haalt of al kocht en opruimde, komt niet terug; alleen de nieuwe avond komt erbij.
        self.db.remove_shopping_item("buy:pesto")
        self.db.set_shopping_check("buy:pasta", True)
        self.db.clear_bought_items()
        self.assertEqual(self.db.put_dinners_on_list(["2026-09-21", "2026-09-22"]), ["2026-09-22"])
        self.assertEqual({i["key"] for i in self.db.shopping_list()}, {"buy:basilicum", "buy:ui"})

    def test_reset_clears_evenings_but_keeps_what_is_bought(self):
        pasta = self.db.create_recipe(PASTA)
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner("2026-09-22", pasta["id"])  # al geweest: blijft staan
        self.db.choose_dinner("2026-09-23", soup["id"])
        self.db.add_suggested_option("2026-09-24", {"name": "Risotto"})
        self.db.set_special_dinner("2026-09-25", "uiteten")
        self.db.put_dinners_on_list(["2026-09-22", "2026-09-23"])
        self.db.set_shopping_check("buy:ui", True)  # ui is al gekocht
        self.db.add_shopping_item("Melk")

        self.db.reset_dinners(["2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"])
        menu = self.db.get_week_menu("2026-09-23")
        self.assertEqual([c["date"] for c in menu["choices"]], ["2026-09-22"])
        self.assertEqual([o["date"] for o in menu["options"]], ["2026-09-22"])
        self.assertEqual(menu["specials"], [])
        self.assertEqual({i["key"] for i in self.db.shopping_list()},
                         {"buy:pasta", "buy:pesto", "buy:basilicum", "bought:ui", "buy:melk"})
        self.assertEqual({r["name"] for r in self.db.list_recipes()}, {"Pasta pesto", "Soep"})

        before = self.db.shopping_list()
        self.db.choose_dinner("2026-09-23", pasta["id"])  # opnieuw gekozen: pas op de lijst na de knop
        self.assertEqual(self.db.shopping_list(), before)
        self.assertEqual(self.db.put_dinners_on_list(["2026-09-23"]), ["2026-09-23"])
        self.assertEqual({i["key"]: i["quantity"] for i in self.db.shopping_list()}["buy:pasta"], 400)

    def test_changing_or_deleting_a_recipe_updates_the_list(self):
        soup = self.db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
        self.db.choose_dinner("2026-09-21", soup["id"])
        self.db.put_dinners_on_list(["2026-09-21"])
        self.db.update_recipe(soup["id"], {"name": "Soep", "ingredients": [{"name": "prei", "quantity": 2, "unit": ""}]})
        self.assertEqual([i["key"] for i in self.db.shopping_list()], ["buy:prei"])
        self.db.delete_recipe(soup["id"])
        self.assertEqual(self.db.shopping_list(), [])

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
        self.db.put_dinners_on_list(["2026-09-22"])
        self.assertEqual({i["key"]: i["quantity"] for i in self.db.shopping_list()}["buy:pasta"], 400)

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

    def test_dinners_chosen_before_the_list_button_stay_on_the_list(self):
        """Vroeger kwam elk gekozen avondeten vanzelf op de lijst; die avonden blijft de lijst volgen."""
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            db = Database(path)
            soup = db.create_recipe({"name": "Soep", "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]})
            db.choose_dinner("2026-09-21", soup["id"])
            conn = sqlite3.connect(path)
            conn.execute("DROP TABLE listed_days")  # zoals een database van vóór de knop
            conn.commit()
            conn.close()

            db = Database(path)
            self.assertTrue(db.get_week_menu("2026-09-21")["choices"][0]["listed"])
            self.assertEqual(db.put_dinners_on_list(["2026-09-21"]), [])  # staat er al op
            db.choose_dinner("2026-09-21", soup["id"], servings=4)  # verandert de avond, dan de lijst ook
            self.assertEqual([(i["key"], i["quantity"]) for i in db.shopping_list()], [("buy:ui", 2)])

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
        cls.api = ApiClient(db=Database(":memory:"))
        cls.base = cls.api.base

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def pasta_on_list(self):
        items = {i["key"]: i["quantity"] for i in self.call("GET", "/api/shopping")[1]["items"]}
        return items.get("buy:pasta") or 0

    def test_full_flow(self):
        pasta_before = self.pasta_on_list()  # andere tests kunnen ook pasta op de (ene) lijst zetten
        status, recipe = self.call("POST", "/api/recipes", PASTA)
        self.assertEqual(status, 200)
        status, option = self.call("POST", "/api/menu/options", {"date": "2026-09-23", "recipe_id": recipe["id"]})
        self.assertEqual(status, 200)
        status, _ = self.call("POST", f"/api/menu/options/{option['id']}/choose", {"servings": 4})
        self.assertEqual(status, 200)
        status, menu = self.call("GET", "/api/menu?week=2026-09-23")
        self.assertEqual(menu["days"][0], "2026-09-21")
        self.assertEqual((menu["choices"][0]["recipe_name"], menu["choices"][0]["listed"]), ("Pasta pesto", False))
        self.assertEqual(self.pasta_on_list(), pasta_before)  # kiezen zet nog niets op de lijst
        status, result = self.call("POST", "/api/menu/to-list", {"week": "2026-09-23", "today": "2026-09-21"})
        self.assertEqual((status, result["added"]), (200, ["2026-09-23"]))
        self.assertEqual(self.pasta_on_list() - pasta_before, 400)

        self.assertEqual(self.call("DELETE", "/api/menu/choice?date=2026-09-23")[0], 200)
        self.assertEqual(self.pasta_on_list(), pasta_before)  # keuze ongedaan: weer van de lijst
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

    def test_to_list_and_reset_skip_evenings_that_have_been(self):
        _, recipe = self.call("POST", "/api/recipes", {**PASTA, "name": "Pasta van augustus"})
        for day in ("2026-08-03", "2026-08-05"):  # maandag en woensdag
            _, option = self.call("POST", "/api/menu/options", {"date": day, "recipe_id": recipe["id"]})
            self.call("POST", f"/api/menu/options/{option['id']}/choose", {})
        week = {"week": "2026-08-05", "today": "2026-08-04"}  # op dinsdag: maandag is al geweest
        self.assertEqual(self.call("POST", "/api/menu/to-list", week)[1]["added"], ["2026-08-05"])
        self.assertEqual(self.call("POST", "/api/menu/reset", week)[0], 200)
        menu = self.call("GET", "/api/menu?week=2026-08-03")[1]
        self.assertEqual([c["date"] for c in menu["choices"]], ["2026-08-03"])
        self.assertEqual([o["date"] for o in menu["options"]], ["2026-08-03"])
        self.assertEqual(self.call("POST", "/api/menu/reset", {"week": "2026-08-03", "today": "dinsdag"})[0], 400)

    def test_errors_are_json(self):
        self.assertEqual(self.call("GET", "/api/recipes/9999")[0], 404)
        self.assertEqual(self.call("GET", "/api/menu")[0], 400)
        self.assertEqual(self.call("POST", "/api/menu/options", {"date": "2026-09-23", "recipe_id": 9999})[0], 404)
        self.assertEqual(self.call("POST", "/api/menu/options/9999/choose", {})[0], 404)
        self.assertEqual(self.call("POST", "/api/recipes", {"name": ""})[0], 400)

    def test_serves_frontend(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn(b"MonEat", res.read())
        with urllib.request.urlopen(self.base + "/../mealplanner/db/base.py") as res:
            self.assertNotIn(b"sqlite3", res.read())

    def test_scripts_have_a_version_in_their_address(self):
        """Na een update laadt de pagina nooit oude scripts uit een cache: elke versie heeft eigen adressen."""
        with urllib.request.urlopen(self.base + "/") as res:
            page = res.read().decode()
            self.assertEqual(res.headers["Cache-Control"], "no-cache")
        match = re.search(r'src="(/v/[0-9a-f]{10}/js/main\.js)"', page)
        self.assertIsNotNone(match)
        self.assertNotIn('href="/css/', page)
        with urllib.request.urlopen(self.base + match.group(1)) as res:
            self.assertIn(b"import", res.read())
            self.assertIn("immutable", res.headers["Cache-Control"])
        with urllib.request.urlopen(self.base + "/v/0000000000/js/main.js") as res:  # oude versie: niet lang bewaren
            self.assertEqual(res.headers["Cache-Control"], "no-cache")
        with urllib.request.urlopen(self.base + "/v/x/../../mealplanner/db/base.py") as res:
            self.assertNotIn(b"sqlite3", res.read())


if __name__ == "__main__":
    unittest.main()
