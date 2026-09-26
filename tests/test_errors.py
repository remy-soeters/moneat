"""Foutmeldingen: duidelijke meldingen van Gemini en Claude, en een logboek met de precieze fout."""

import unittest
from types import SimpleNamespace
from unittest import mock

from mealplanner import ai, gemini
from mealplanner.actions import describe_action
from mealplanner.db import Database
from tests.helpers import api_test


class ErrorLogTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.api = api_test(self, db=self.db)

    def test_ai_errors_land_in_the_log_with_the_exact_reply(self):
        error = ai.AIUnavailable("Je Gemini-tegoed is op.", 'HTTP 429: {"message": "Your prepayment credits are depleted"}', "Gemini")
        with mock.patch.object(ai, "generate_recipe", side_effect=error):
            for _ in range(2):
                status, body = self.api.call("POST", "/api/recipes/generate", {"prompt": "soep"})
                self.assertEqual((status, body["error"]), (503, "Je Gemini-tegoed is op."))
        (entry,) = self.api.call("GET", "/api/errors")[1]["errors"]  # twee keer dezelfde fout: één regel
        self.assertEqual((entry["source"], entry["action"], entry["user"], entry["count"]),
                         ("Gemini", "Recept laten bedenken", "Remy", 2))
        self.assertIn("prepayment credits", entry["detail"])

    def test_browser_reports_what_the_server_never_saw(self):
        status, _ = self.api.call("POST", "/api/errors", {"errors": [
            {"method": "POST", "path": "/api/menu/fill", "message": "Geen antwoord van MonEat",
             "detail": "TypeError: Failed to fetch (na 61 s)", "at": "2026-09-25T12:00:00.000Z"},
            "rommel",
        ]})
        self.assertEqual(status, 200)
        (entry,) = self.api.call("GET", "/api/errors")[1]["errors"]
        self.assertEqual((entry["source"], entry["action"], entry["created_at"]),
                         ("Browser", "Opties voor het weekmenu", "2026-09-25 12:00:00"))
        self.assertIn("Failed to fetch", entry["detail"])
        self.assertEqual(self.api.call("DELETE", "/api/errors")[0], 200)
        self.assertEqual(self.api.call("GET", "/api/errors")[1]["errors"], [])

    def test_actions_in_words(self):
        self.assertEqual(describe_action("GET", "/api/shopping"), "Boodschappenlijst openen")
        self.assertEqual(describe_action("POST", "/api/recipes/12/photo"), "Foto maken")
        self.assertEqual(describe_action("PUT", "/api/recipes/12"), "PUT /api/recipes/12")

    def test_keeps_the_latest_entries(self):
        for i in range(205):
            self.db.log_error("Server", "test", f"fout {i}")
        errors = self.db.recent_errors()
        self.assertEqual((len(errors), errors[0]["message"], errors[-1]["message"]), (200, "fout 204", "fout 5"))


class ExplainTest(unittest.TestCase):
    """Wat Google of Anthropic antwoordt, wordt een melding waar je iets mee kunt."""

    def test_gemini(self):
        cases = [
            (429, {"message": "Your prepayment credits are depleted.", "status": "RESOURCE_EXHAUSTED"}, "tegoed is op"),
            (429, {"message": "Quota exceeded for metric: generate_content_free_tier_requests, limit: 0, "
                               "model: gemini-2.5-flash-image"}, "betalen nodig"),
            (429, {"message": "You exceeded your current quota, please check your plan and billing details.",
                   "details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                               {"retryDelay": "34s"}]}, "per minuut is bereikt. Probeer het over 34 seconden"),
            (429, {"message": "You exceeded your current quota",
                   "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]},
             "voor vandaag is bereikt"),
            (400, {"message": "Gemini API free tier is not available in your country. Please enable billing.",
                   "status": "FAILED_PRECONDITION"}, "betalen nodig"),
            (400, {"message": "API key not valid. Please pass a valid API key."}, "niet geaccepteerd"),
            (503, {"message": "The model is overloaded."}, "te druk"),
        ]
        for status, error, expected in cases:
            with self.subTest(error["message"][:40]):
                self.assertIn(expected, gemini._explain(status, error))

    def test_claude_empty_balance(self):
        error = SimpleNamespace(status_code=400, request_id="req_123", body={"type": "error"},
                                message="Your credit balance is too low to access the Anthropic API.")
        failure = ai._claude_error(error)
        self.assertIn("tegoed is op", str(failure))
        self.assertEqual(failure.source, "Claude")
        self.assertIn("req_123", failure.detail)


if __name__ == "__main__":
    unittest.main()
