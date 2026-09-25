"""Favorieten en beoordelingen na het koken."""

import unittest
from datetime import date, timedelta
from unittest import mock

from mealplanner import ai
from tests.helpers import PASSWORD, ApiClient, api_test

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


class RatingsTest(unittest.TestCase):
    def setUp(self):
        self.api = api_test(self)
        self.db = self.api.db
        self.soup = self.api.call("POST", "/api/recipes", {"name": "Soep"})[1]

    def test_favorite_is_per_person(self):
        status, recipe = self.api.call("PUT", f"/api/recipes/{self.soup['id']}/favorite", {"favorite": True})
        self.assertEqual((status, recipe["favorite"]), (200, True))
        self.assertTrue(self.api.call("GET", "/api/recipes")[1][0]["favorite"])
        self.api.call("POST", "/api/users", {"username": "sam", "password": "nog-een-lang-wachtwoord"})
        sam = ApiClient(user=None, db=self.db, images=self.api.images)
        self.addCleanup(sam.close)
        sam.call("POST", "/api/auth/login", {"username": "sam", "password": "nog-een-lang-wachtwoord"})
        self.assertFalse(sam.call("GET", "/api/recipes")[1][0]["favorite"])  # Sam heeft het niet als favoriet
        self.assertFalse(self.api.call("PUT", f"/api/recipes/{self.soup['id']}/favorite", {"favorite": False})[1]["favorite"])

    def test_rating_average_and_update_same_day(self):
        url = f"/api/recipes/{self.soup['id']}/rating"
        self.assertEqual(self.api.call("POST", url, {"stars": 6})[0], 400)
        self.api.call("POST", url, {"stars": 3, "date": YESTERDAY})
        recipe = self.api.call("POST", url, {"stars": 5, "date": YESTERDAY, "note": "Toch heerlijk"})[1]  # zelfde dag: bijgewerkt
        self.assertEqual((recipe["rating"], recipe["rating_count"], recipe["my_rating"]), (5, 1, 5))
        self.api.call("POST", url, {"stars": 4, "date": TODAY.isoformat()})
        recipe = self.api.call("GET", f"/api/recipes/{self.soup['id']}")[1]
        self.assertEqual((recipe["rating"], recipe["rating_count"], recipe["my_rating"]), (4.5, 2, 4))
        self.assertEqual(recipe["ratings"][1]["note"], "Toch heerlijk")

    def test_home_asks_about_yesterday_until_rated(self):
        self.db.choose_dinner(YESTERDAY, self.soup["id"])
        home = self.api.call("GET", f"/api/home?today={TODAY.isoformat()}")[1]
        self.assertEqual((home["rate"]["date"], home["rate"]["recipe"]["name"]), (YESTERDAY, "Soep"))
        self.api.call("POST", f"/api/recipes/{self.soup['id']}/rating", {"stars": 4, "date": YESTERDAY})
        self.assertIsNone(self.api.call("GET", f"/api/home?today={TODAY.isoformat()}")[1]["rate"])

    def test_ai_sees_favorites_and_ratings(self):
        self.api.call("PUT", f"/api/recipes/{self.soup['id']}/favorite", {"favorite": True})
        self.api.call("POST", f"/api/recipes/{self.soup['id']}/rating", {"stars": 5, "date": YESTERDAY})
        with mock.patch.object(ai, "_ask", return_value={"suggestions": []}) as ask:
            self.api.call("POST", "/api/menu/fill", {"week": TODAY.isoformat(), "dates": [TODAY.isoformat()]})
        prompt = ask.call_args.args[1]
        self.assertIn('"favoriet": true', prompt)
        self.assertIn('"beoordeling": 5', prompt)


if __name__ == "__main__":
    unittest.main()
