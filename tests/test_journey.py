"""Plannen per dag: bijzondere avonden, 'andere opties' en de startpagina."""

import unittest
from datetime import date, timedelta
from unittest import mock

from mealplanner import ai
from mealplanner.db import Database
from tests.helpers import api_test

TODAY = date.today()
DAY = (TODAY + timedelta(days=1)).isoformat()
SOUP = {"name": "Soep", "servings": 2, "ingredients": [{"name": "prei", "quantity": 2, "unit": ""}]}


def idea(name):
    return {"name": name, "servings": 2, "prep_minutes": 20, "tags": "", "instructions": "1. Koken.",
            "ingredients": [{"name": "ui", "quantity": 1, "unit": ""}]}


class SpecialDinnerTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.soup = self.db.create_recipe(SOUP)

    def test_special_replaces_choice_and_its_shopping(self):
        self.db.choose_dinner(DAY, self.soup["id"])
        self.assertEqual([i["name"] for i in self.db.shopping_list()], ["Prei"])
        self.db.set_special_dinner(DAY, "uiteten")
        menu = self.db.get_week_menu(DAY)
        self.assertEqual(menu["choices"], [])
        self.assertEqual([(s["date"], s["kind"], s["label"]) for s in menu["specials"]], [(DAY, "uiteten", "Uit eten")])
        self.assertEqual(self.db.shopping_list(), [])  # uit eten: niets te koop

        self.db.choose_dinner(DAY, self.soup["id"])  # toch koken: bijzondere avond vervalt
        self.assertEqual(self.db.get_week_menu(DAY)["specials"], [])
        self.db.set_special_dinner(DAY, "vriezer")
        self.db.clear_dinner_choice(DAY)
        self.assertEqual(self.db.get_week_menu(DAY)["specials"], [])
        with self.assertRaises(ValueError):
            self.db.set_special_dinner(DAY, "iets-anders")

    def test_ai_options_leave_out_own_and_chosen(self):
        own = self.db.add_menu_option(DAY, self.soup["id"])
        stew = self.db.create_recipe({**SOUP, "name": "Stoof"})
        self.db.add_menu_option(DAY, stew["id"], "past goed", source="claude")
        self.db.add_suggested_option(DAY, idea("Curry"), "lekker")
        chosen = self.db.add_suggested_option(DAY, idea("Pasta"), "snel")
        self.db.choose_option(chosen)
        self.assertEqual(sorted(o["name"] for o in self.db.ai_options(DAY)), ["Curry", "Stoof"])
        self.assertIn(own, [o["id"] for o in self.db.get_week_menu(DAY)["options"]])

    def test_upcoming_dinners(self):
        self.db.choose_dinner(TODAY.isoformat(), self.soup["id"], servings=3)
        self.db.set_special_dinner(DAY, "afhalen")
        days = self.db.upcoming_dinners(TODAY.isoformat(), 7)
        self.assertEqual(len(days), 7)
        self.assertEqual((days[0]["recipe"]["name"], days[0]["servings"]), ("Soep", 3))
        self.assertEqual(days[0]["recipe"]["ingredients"][0]["name"], "prei")
        self.assertEqual(days[1]["special"]["label"], "Afhalen")
        self.assertIsNone(days[2]["recipe"])


class JourneyApiTest(unittest.TestCase):
    def setUp(self):
        self.api = api_test(self)
        self.db = self.api.db

    def test_refresh_replaces_ai_options_and_avoids_them(self):
        self.db.add_suggested_option(DAY, idea("Curry"), "lekker")
        self.db.add_suggested_option(DAY, idea("Pasta"), "snel")
        new = [{"date": DAY, "existing_recipe_id": None, "new_recipe": idea(n), "reason": "nieuw"} for n in ("Wok", "Soep", "Salade")]
        with mock.patch.object(ai, "suggest_menu_options", return_value=new) as suggest:
            status, body = self.api.call("POST", "/api/menu/refresh", {"date": DAY, "per_day": 3, "servings": 2})
        self.assertEqual((status, body), (200, {"added": 3, "removed": 2}))
        self.assertEqual(sorted(suggest.call_args.kwargs["avoid"]), ["Curry", "Pasta"])
        self.assertEqual(suggest.call_args.args[1], {DAY: 3})
        names = sorted(o["name"] for o in self.db.get_week_menu(DAY)["options"])
        self.assertEqual(names, ["Salade", "Soep", "Wok"])
        self.assertEqual(self.api.call("POST", "/api/menu/refresh", {"date": "gisteren"})[0], 400)

    def test_failed_refresh_keeps_old_options(self):
        self.db.add_suggested_option(DAY, idea("Curry"), "lekker")
        with mock.patch.object(ai, "suggest_menu_options", side_effect=ai.AIUnavailable("limiet bereikt")):
            status, body = self.api.call("POST", "/api/menu/refresh", {"date": DAY})
        self.assertEqual((status, body["error"]), (503, "limiet bereikt"))
        self.assertEqual([o["name"] for o in self.db.get_week_menu(DAY)["options"]], ["Curry"])

    def test_fill_only_given_days_and_skips_special_days(self):
        other = (TODAY + timedelta(days=2)).isoformat()
        self.db.set_special_dinner(other, "vriezer")
        with mock.patch.object(ai, "suggest_menu_options", return_value=[]) as suggest:
            self.api.call("POST", "/api/menu/fill", {"week": DAY, "dates": [DAY, other], "per_day": 2})
        self.assertEqual(suggest.call_args.args[1], {DAY: 2})  # alleen gevraagde avonden, en niet de vriezer-avond

    def test_special_and_home(self):
        soup = self.db.create_recipe(SOUP)
        self.db.choose_dinner(TODAY.isoformat(), soup["id"])
        self.assertEqual(self.api.call("POST", "/api/menu/special", {"date": DAY, "kind": "restjes"})[0], 200)
        self.assertEqual(self.api.call("POST", "/api/menu/special", {"date": DAY, "kind": "pizza"})[0], 400)
        status, home = self.api.call("GET", f"/api/home?today={TODAY.isoformat()}")
        self.assertEqual(status, 200)
        self.assertEqual(home["days"][0]["recipe"]["name"], "Soep")
        self.assertEqual(home["days"][1]["special"]["kind"], "restjes")
        self.assertEqual(home["to_buy"], 1)


if __name__ == "__main__":
    unittest.main()


class NoRepeatsTest(unittest.TestCase):
    """Wat je deze week niet wilde, komt die week niet terug; en geen gerecht op twee avonden."""

    def setUp(self):
        self.api = api_test(self)
        self.db = self.api.db
        first = TODAY + timedelta(days=1)
        if first.weekday() == 6:  # zondag: dan maandag en dinsdag, zodat beide avonden in dezelfde week vallen
            first += timedelta(days=1)
        self.day, self.next_day = first.isoformat(), (first + timedelta(days=1)).isoformat()

    def suggest(self, day, *names):
        return [{"date": day, "existing_recipe_id": None, "new_recipe": idea(n), "reason": "nieuw"} for n in names]

    def test_refreshed_dishes_stay_away_for_the_week(self):
        self.db.add_suggested_option(self.day, idea("Curry"), "lekker")
        with mock.patch.object(ai, "suggest_menu_options", return_value=self.suggest(self.day, "Wok")):
            self.api.call("POST", "/api/menu/refresh", {"date": self.day, "per_day": 1})
        self.assertEqual(self.db.passed_dishes(self.day), ["Curry"])

        # Een andere avond: Curry is afgewezen en Wok staat al op het menu, dus die vallen af.
        returned = self.suggest(self.next_day, "curry", "Wok", "Salade", "Salade")
        with mock.patch.object(ai, "suggest_menu_options", return_value=returned) as suggest:
            status, body = self.api.call("POST", "/api/menu/fill", {"week": self.next_day, "dates": [self.next_day], "per_day": 3})
        self.assertEqual((status, body), (200, {"added": 1}))
        self.assertIn("Curry", suggest.call_args.kwargs["avoid"])
        options = [o["name"] for o in self.db.get_week_menu(self.next_day)["options"] if o["date"] == self.next_day]
        self.assertEqual(options, ["Salade"])

    def test_left_over_options_of_a_chosen_day_count_as_passed(self):
        chosen = self.db.add_suggested_option(self.day, idea("Pasta"), "snel")
        self.db.add_suggested_option(self.day, idea("Stamppot"), "stevig")
        self.db.choose_option(chosen)
        with mock.patch.object(ai, "suggest_menu_options", return_value=self.suggest(self.next_day, "Stamppot", "Pasta", "Wraps")) as suggest:
            self.api.call("POST", "/api/menu/fill", {"week": self.next_day, "dates": [self.next_day], "per_day": 3})
        self.assertEqual(suggest.call_args.kwargs["avoid"], ["Stamppot"])
        options = [o["name"] for o in self.db.get_week_menu(self.next_day)["options"] if o["date"] == self.next_day]
        self.assertEqual(options, ["Wraps"])
