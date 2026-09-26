import tempfile
import threading
import time
import unittest
from unittest import mock

from mealplanner import ai, setting_keys
from mealplanner.db import Database
from mealplanner.images import ImageStore
from mealplanner.preloader import SwipePreloader
from tests.test_import import tiny_png
from tests.test_swipe import idea

PREFS = {"diet": "alles", "cuisines": [], "max_minutes": None, "avoid": ""}


class PreloaderTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.images = ImageStore(tempfile.mkdtemp())
        self.prefs = dict(PREFS)
        self.target = 10
        self.preloader = SwipePreloader(
            self.db, self.images, self.images.delete, lambda: self.prefs, lambda: self.target
        )
        self.counter = 0
        patches = [
            mock.patch.object(ai, "gemini_configured", return_value=True),
            mock.patch.object(ai, "swipe_recipes", side_effect=self.fake_recipes),
            mock.patch.object(ai, "generate_photo", side_effect=self.fake_photo),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.photo_threads = set()

    def fake_recipes(self, prefs, count, exclude=(), servings=2):
        self.requested = (count, servings)
        self.counter += 1
        return [idea(f"Gerecht {self.counter}-{i}") for i in range(count)]

    def fake_photo(self, recipe):
        self.photo_threads.add(threading.current_thread().name)
        time.sleep(0.05)
        return tiny_png()

    def run_preloader(self, **kwargs):
        self.preloader.kick(**kwargs)
        if self.preloader.thread:
            self.preloader.thread.join(timeout=10)

    def test_fills_up_to_target_with_photos(self):
        self.run_preloader(servings=3)
        cards = self.db.pending_swipe_cards()
        self.assertEqual(self.requested, (12, 3))  # 10 nodig + 2 reserve
        self.assertGreaterEqual(len(cards), 10)
        self.assertTrue(all(c["image"] for c in cards[:10]))
        self.assertGreater(len(self.photo_threads), 1)  # foto's worden tegelijk gemaakt
        self.assertIsNone(self.preloader.status()["error"])

    def test_does_nothing_without_preferences_or_when_full(self):
        self.prefs = {}
        self.run_preloader()
        self.assertEqual(self.db.pending_swipe_cards(), [])
        self.prefs = dict(PREFS)
        self.run_preloader()
        calls = self.counter
        self.run_preloader()  # voorraad is al vol: geen nieuw AI-verzoek
        self.assertEqual(self.counter, calls)

    def test_asks_again_when_ideas_were_already_seen(self):
        self.db.add_swipe_cards([idea("Oud gerecht")])
        self.db.swipe(self.db.pending_swipe_cards()[0]["id"], liked=False)
        answers = iter([[idea("Oud gerecht")] * 12, [idea(f"Nieuw {i}") for i in range(12)]])
        ai.swipe_recipes.side_effect = lambda *a, **k: next(answers)
        self.run_preloader()
        self.assertEqual(ai.swipe_recipes.call_count, 2)
        self.assertEqual(len(self.db.pending_swipe_cards()), 12)

    def test_respects_chosen_target(self):
        self.target = 5
        self.run_preloader()
        self.assertEqual(self.requested[0], 7)

    def test_stops_making_photos_after_failure(self):
        ai.generate_photo.side_effect = ai.AIUnavailable("betalen nodig")
        self.run_preloader()
        status = self.preloader.status()
        self.assertEqual((status["photos_failed"], status["photos_enabled"]), ("betalen nodig", False))
        self.assertLessEqual(ai.generate_photo.call_count, 3)  # hooguit de eerste gelijktijdige pogingen
        self.assertTrue(self.db.pending_swipe_cards())  # kaarten zonder foto zijn er wel
        self.run_preloader(retry=True)
        self.assertIsNotNone(self.preloader.status()["photos_failed"])  # opnieuw geprobeerd, nog steeds mis

    def test_no_photos_when_auto_images_is_off(self):
        with mock.patch.object(ai, "_setting", lambda key, default=None: "off" if key == setting_keys.AUTO_IMAGES else default):
            self.run_preloader()
            self.assertFalse(self.preloader.status()["photos_enabled"])
        self.assertEqual(ai.generate_photo.call_count, 0)
        self.assertGreaterEqual(len(self.db.pending_swipe_cards()), 10)  # wel gerechten, zonder foto

    def test_text_errors_are_reported(self):
        ai.swipe_recipes.side_effect = ai.AIUnavailable("geen sleutel")
        self.run_preloader()
        self.assertEqual(self.preloader.status()["error"], "geen sleutel")

    def test_late_photo_goes_to_saved_recipe(self):
        self.db.add_swipe_cards([idea("Dahl")])
        card = self.db.pending_swipe_cards()[0]
        recipe = self.db.swipe(card["id"], liked=True)
        self.assertEqual(recipe["image"], "")
        self.preloader._photo(card)
        self.assertTrue(self.db.get_recipe(recipe["id"])["image"])

    def test_photo_for_discarded_card_is_removed(self):
        self.db.add_swipe_cards([idea("Dahl")])
        card = self.db.pending_swipe_cards()[0]
        self.db.clear_pending_swipe_cards()
        self.preloader._photo(card)
        self.assertEqual(list(self.images.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
