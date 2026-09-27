"""Verbruik van de AI (Instellingen → Foto's en iconen) en iconen die per product hergebruikt worden."""

import tempfile
import unittest
from unittest import mock

from mealplanner import ai, gemini
from mealplanner.db import Database
from mealplanner.icons import IconMaker
from mealplanner.images import ImageStore
from mealplanner.db.schema import migrate
from mealplanner.setting_keys import GEMINI_KEY, GEMINI_TEXT_KEY, TEXT_PROVIDER
from tests.helpers import ApiClient, api_test
from tests.test_import import tiny_png

ICON = "/images/" + "c" * 32 + ".jpg"
IDEAS = {"intro": "", "ideas": [{"description": "", "recipe": {"name": "Soep", "servings": 2, "prep_minutes": 20,
                                                              "tags": "", "instructions": "1. Koken.", "ingredients": []}}]}


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        settings = {GEMINI_KEY: "betaald", GEMINI_TEXT_KEY: "gratis", TEXT_PROVIDER: "gemini"}
        old_setting, old_record = ai._setting, ai._record
        self.addCleanup(lambda: (ai.set_settings(old_setting), ai.set_usage_recorder(old_record)))
        ai.set_settings(lambda key, default=None: settings.get(key, default))
        ai.set_usage_recorder(self.db.log_ai_usage)

    def test_every_request_is_counted_with_purpose_and_price(self):
        with mock.patch.object(gemini, "generate_image", return_value=b"jpg"):
            ai.generate_photo({"name": "Soep"})
            with ai.usage("Iconen voor boodschappen", auto=True):
                ai.generate_icon("Tomaten")
        with mock.patch.object(gemini, "generate_json", return_value=IDEAS):
            ai.inspiration("herfst")
        with mock.patch.object(gemini, "generate_image", side_effect=gemini.GeminiError("limiet")):
            with self.assertRaises(ai.AIUnavailable):
                ai.generate_photo({"name": "Soep"})  # mislukt: telt niet mee

        report = self.db.ai_usage_report(7)
        totals = report["totals"]
        self.assertEqual((totals["foto"], totals["icoon"], totals["tekst"], totals["auto"], totals["free_text"]), (1, 1, 1, 1, 1))
        self.assertAlmostEqual(totals["cost"], 0.06)
        purposes = {p["purpose"]: p for p in report["purposes"]}
        self.assertEqual(set(purposes), {"Foto bij recept", "Iconen voor boodschappen", "Inspiratie"})
        self.assertTrue(purposes["Iconen voor boodschappen"]["auto"])
        self.assertFalse(purposes["Foto bij recept"]["auto"])
        self.assertEqual((purposes["Inspiratie"]["kind"], purposes["Inspiratie"]["free"]), ("tekst", 1))
        self.assertEqual(len(report["per_day"]), 1)
        self.assertEqual((report["per_day"][0]["foto"], report["per_day"][0]["auto"]), (1, 1))

    def test_background_tasks_count_as_automatic(self):
        maker = IconMaker(self.db, ImageStore(tempfile.mkdtemp()))
        with mock.patch.object(gemini, "generate_image", return_value=tiny_png()):
            maker._draw("Uien")
        self.assertEqual([(p["purpose"], p["auto"]) for p in self.db.ai_usage_report()["purposes"]],
                         [("Iconen voor boodschappen", True)])


class UsageApiTest(unittest.TestCase):
    def test_only_for_admins(self):
        admin = api_test(self)
        admin.db.log_ai_usage({"kind": "foto", "purpose": "Foto bij recept", "cost": 0.03})
        status, report = admin.call("GET", "/api/usage?days=30")
        self.assertEqual((status, report["days"], report["totals"]["foto"]), (200, 30, 1))
        member = ApiClient(user="sam", admin=False)
        self.addCleanup(member.close)
        self.assertEqual(member.call("GET", "/api/usage")[0], 403)


class IconReuseTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_one_icon_per_product(self):
        self.db.set_product_icon("Tomaten", ICON)
        icons = self.db.product_icons(["Tomaat", "tomaten", "Verse tomaten", "Tomaten (blik)"])
        self.assertEqual(icons, {"Tomaat": ICON, "tomaten": ICON, "Verse tomaten": ICON})  # uit blik is een ander product

    def test_existing_icons_are_converted_once(self):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'icon_keys_v2'")
            conn.executemany("INSERT INTO product_icons (key, image) VALUES (?, ?)",
                             [("tomaten", ""), ("tomaat", ICON), ("rode uien", ICON), ("tomaten (blik)", ICON)])
            migrate(conn)
            rows = dict(conn.execute("SELECT key, image FROM product_icons").fetchall())
        self.assertEqual(rows, {"tomat": ICON, "rode ui": ICON, "tomat blik": ICON})  # het plaatje wint van de emoji
        self.assertEqual(self.db.product_icons(["Tomaten"]), {"Tomaten": ICON})

    def test_suggestions_do_not_draw_new_icons(self):
        client = api_test(self)
        with mock.patch.object(client.app.icon_maker, "request") as request:
            self.assertEqual(client.call("GET", "/api/shopping/suggestions")[0], 200)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
