import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.helpers import ApiClient, api_test
from mealplanner import ai, gemini, setting_keys
from mealplanner.db import Database

KEY = "sk-ant-api03-" + "a" * 40 + "WXYZ"
GEMINI_KEY = "AIzaSyB" + "b" * 28 + "9876"


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.api = api_test(self, db=self.db)
        self.base = self.api.base

    def call(self, method, path, body=None, **kwargs):
        return self.api.call(method, path, body, **kwargs)

    def test_save_mask_and_delete_keys(self):
        status, settings = self.call("GET", "/api/settings")
        self.assertEqual((status, settings["claude"]["set"], settings["gemini"]["set"]), (200, False, False))
        self.assertEqual(settings["text_provider"], "claude")

        status, settings = self.call("PUT", "/api/settings", {"claude_api_key": f"  {KEY}  ", "gemini_api_key": GEMINI_KEY})
        self.assertEqual(status, 200)
        self.assertEqual((settings["claude"]["hint"], settings["gemini"]["hint"]), ("sk-ant-…WXYZ", "AIzaSyB…9876"))
        self.assertEqual(self.db.get_setting("anthropic_api_key"), KEY)

        # De volledige sleutels komen nergens in een antwoord terug.
        for response in (settings, self.call("GET", "/api/settings")[1]):
            self.assertNotIn(KEY, json.dumps(response))
            self.assertNotIn(GEMINI_KEY, json.dumps(response))

        status, settings = self.call("DELETE", "/api/settings/key/gemini")
        self.assertEqual((status, settings["gemini"]["set"], settings["claude"]["set"]), (200, False, True))
        self.assertEqual(self.call("DELETE", "/api/settings/key/iets")[0], 404)

    def test_rejects_things_that_are_not_keys(self):
        for bad in ("", "hallo", "sk-ant-kort", "sk-proj-" + "a" * 40):
            self.assertEqual(self.call("PUT", "/api/settings", {"claude_api_key": bad})[0], 400, bad)
        self.assertEqual(self.call("PUT", "/api/settings", {"gemini_api_key": "kort"})[0], 400)

    def test_accepts_new_gemini_key_format(self):
        new_style = "AQ.Ab8" + "x" * 40 + "_-yZ"
        status, settings = self.call("PUT", "/api/settings", {"gemini_api_key": new_style})
        self.assertEqual((status, settings["gemini"]["hint"]), (200, "AQ.Ab8x…_-yZ"))

    def test_provider_and_models(self):
        status, settings = self.call("PUT", "/api/settings", {"text_provider": "gemini", "gemini_text_model": "gemini-9-flash"})
        self.assertEqual((settings["text_provider"], settings["gemini"]["text_model"]), ("gemini", "gemini-9-flash"))
        self.assertEqual(ai.provider_name(), "Gemini")
        settings = self.call("PUT", "/api/settings", {"gemini_text_model": ""})[1]
        self.assertEqual(settings["gemini"]["text_model"], settings["gemini"]["default_text_model"])
        self.assertEqual(self.call("PUT", "/api/settings", {"text_provider": "chatgpt"})[0], 400)
        self.assertEqual(self.call("PUT", "/api/settings", {"gemini_image_model": "rm -rf /"})[0], 400)

    def test_auto_images_switch(self):
        self.db.set_setting(setting_keys.GEMINI_KEY, "AIza" + "x" * 35)
        self.assertTrue(self.call("GET", "/api/settings")[1]["auto_images"])
        self.assertTrue(ai.auto_images())
        settings = self.call("PUT", "/api/settings", {"auto_images": False})[1]
        self.assertFalse(settings["auto_images"])
        self.assertFalse(ai.auto_images())
        self.assertFalse(self.call("GET", "/api/shopping")[1]["icons"]["enabled"])
        self.assertTrue(self.call("PUT", "/api/settings", {"auto_images": True})[1]["auto_images"])

    def test_claude_model_choice_shapes_the_request(self):
        ai._latest.clear()
        self.addCleanup(ai._latest.clear)
        settings = self.call("GET", "/api/settings")[1]
        self.assertEqual((settings["claude"]["model"], settings["claude"]["current"]), ("sonnet", "Claude Sonnet 5"))
        self.assertEqual([m["name"] for m in settings["claude"]["models"]], ["Chef Claude Sonnet", "Chef Claude Haiku"])
        self.assertEqual(self.call("PUT", "/api/settings", {"claude_model": "claude-opus-5"})[0], 400)

        def model(id, created, adaptive=True, effort=True):
            return mock.Mock(id=id, display_name=id.replace("claude-", "Claude ").replace("-", " ").title(),
                             created_at=created, max_tokens=128000,
                             capabilities={"thinking": {"types": {"adaptive": {"supported": adaptive}}},
                                           "effort": {"medium": {"supported": effort}}})

        available = [model("claude-sonnet-4-6", 1), model("claude-sonnet-5", 2), model("claude-opus-5", 3),
                     model("claude-haiku-4-5", 1, adaptive=False, effort=False)]

        def sent_options():
            fake = mock.MagicMock()
            fake.models.list.return_value = available
            stream = fake.beta.messages.stream.return_value.__enter__.return_value
            stream.get_final_message.return_value = mock.Mock(
                stop_reason="end_turn", content=[mock.Mock(type="text", text="{}")])
            with mock.patch.object(ai, "_client", return_value=(mock.Mock(), fake)):
                ai._ask_claude("systeem", "vraag", {"type": "object"}, "low")
            return fake.beta.messages.stream.call_args.kwargs

        sonnet = sent_options()  # het nieuwste van de familie, niet Opus
        self.assertEqual((sonnet["model"], sonnet["thinking"], sonnet["output_config"]["effort"], sonnet["max_tokens"]),
                         ("claude-sonnet-5", {"type": "adaptive"}, "low", 64000))
        self.assertNotIn("fallbacks", sonnet)
        self.call("PUT", "/api/settings", {"claude_model": "haiku"})
        haiku = sent_options()
        self.assertEqual(haiku["model"], "claude-haiku-4-5")
        self.assertNotIn("thinking", haiku)  # dat kan Haiku 4.5 volgens de Models API niet
        self.assertNotIn("effort", haiku["output_config"])
        self.assertIn("format", haiku["output_config"])

        # Een nieuwere Haiku verschijnt: die kookt vanaf de volgende dag vanzelf, met wat hij kan.
        available.append(model("claude-haiku-5-5", 9))
        ai._latest.clear()
        newer = sent_options()
        self.assertEqual((newer["model"], newer["thinking"]), ("claude-haiku-5-5", {"type": "adaptive"}))
        self.assertEqual(self.call("GET", "/api/settings")[1]["claude"]["current"], "Claude Haiku 5 5")

    def test_older_claude_choices_and_offline_fallback(self):
        ai._latest.clear()
        self.addCleanup(ai._latest.clear)
        for stored, family in (("claude-opus-5", "sonnet"), ("claude-sonnet-5", "sonnet"), ("claude-haiku-4-5", "haiku")):
            self.db.set_setting(setting_keys.CLAUDE_MODEL, stored)
            self.assertEqual(ai.claude_model()["id"], family)
        broken = mock.Mock()
        broken.models.list.side_effect = RuntimeError("geen verbinding")
        self.assertEqual(ai.latest_claude_model(broken)["id"], "claude-haiku-4-5")  # het standaardmodel

    def test_free_gemini_key_is_used_for_text_only(self):
        paid, free = "AIza" + "p" * 35, "AIza" + "f" * 35
        self.call("PUT", "/api/settings", {"gemini_api_key": paid, "text_provider": "gemini"})
        with mock.patch.object(gemini, "generate_json", return_value={}) as text:
            ai._ask("s", "u", {})
        self.assertEqual(text.call_args.args[0], paid)  # zonder gratis sleutel: de betaalde
        settings = self.call("PUT", "/api/settings", {"gemini_text_api_key": free})[1]
        self.assertTrue(settings["gemini"]["text_key"]["set"])
        self.assertTrue(settings["gemini"]["text_models"])
        with mock.patch.object(gemini, "generate_json", return_value={}) as text, \
                mock.patch.object(gemini, "generate_image", return_value=b"x") as image:
            ai._ask("s", "u", {})
            ai.generate_icon("tomaat")
        self.assertEqual((text.call_args.args[0], image.call_args.args[0]), (free, paid))
        self.assertFalse(self.call("DELETE", "/api/settings/key/gemini_text")[1]["gemini"]["text_key"]["set"])

    def test_free_or_paid_plan_for_chef_gemini(self):
        paid, free = "AIza" + "p" * 35, "AIza" + "f" * 35
        settings = self.call("PUT", "/api/settings", {"gemini_api_key": paid, "text_provider": "gemini"})[1]
        self.assertEqual(settings["gemini_plan"], "paid")  # nog niet gekozen en geen gratis sleutel: betaald
        settings = self.call("PUT", "/api/settings", {"gemini_plan": "free"})[1]
        self.assertEqual(settings["gemini_plan"], "free")
        # Gratis zonder gratis sleutel: een duidelijke melding, en nooit stilletjes de betaalde sleutel.
        with mock.patch.object(gemini, "generate_json", return_value={}) as text:
            with self.assertRaises(ai.AIUnavailable) as error:
                ai._ask("s", "u", {})
        self.assertIn("gratis sleutel", str(error.exception))
        text.assert_not_called()
        self.call("PUT", "/api/settings", {"gemini_text_api_key": free})
        with mock.patch.object(gemini, "generate_json", return_value={}) as text:
            ai._ask("s", "u", {})
        self.assertEqual(text.call_args.args[0], free)
        self.call("PUT", "/api/settings", {"gemini_plan": "paid"})  # betaald, ook al is er een gratis sleutel
        with mock.patch.object(gemini, "generate_json", return_value={}) as text:
            ai._ask("s", "u", {})
        self.assertEqual(text.call_args.args[0], paid)
        self.assertEqual(self.call("PUT", "/api/settings", {"gemini_plan": "gratis"})[0], 400)

    def test_ai_uses_key_from_settings(self):
        self.call("PUT", "/api/settings", {"claude_api_key": KEY})
        self.assertEqual(ai._setting(setting_keys.CLAUDE_KEY), KEY)

    def test_connection_test_reports_problems(self):
        with mock.patch.object(ai, "check_connection", side_effect=ai.AIUnavailable(ai.NO_KEY)):
            status, result = self.call("POST", "/api/settings/test", {})
        self.assertEqual((status, result["error"]), (503, ai.NO_KEY))
        with mock.patch.object(ai, "check_gemini", return_value=None):
            status, result = self.call("POST", "/api/settings/test", {"provider": "gemini"})
        self.assertEqual((status, result["ok"]), (200, True))


@unittest.skipUnless(ai.sdk_installed(), "het anthropic-pakket is niet geïnstalleerd")
class MissingKeyTest(unittest.TestCase):
    def test_missing_key_gives_clear_message(self):
        ai.set_settings(lambda key, default=None: default)
        with mock.patch.dict("os.environ", {}, clear=True):
            for call in (ai.check_connection, lambda: ai.generate_recipe("tosti", 1)):
                with self.assertRaises(ai.AIUnavailable) as ctx:
                    call()
                self.assertEqual(str(ctx.exception), ai.NO_KEY)


if __name__ == "__main__":
    unittest.main()
