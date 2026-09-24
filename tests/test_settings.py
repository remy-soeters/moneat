import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from mealplanner import ai, gemini
from mealplanner.db import Database
from mealplanner.server import make_handler

KEY = "sk-ant-api03-" + "a" * 40 + "WXYZ"
GEMINI_KEY = "AIzaSyB" + "b" * 28 + "9876"


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

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
        self.db.set_setting(ai.GEMINI_KEY, "AIza" + "x" * 35)
        self.assertTrue(self.call("GET", "/api/settings")[1]["auto_images"])
        self.assertTrue(ai.auto_images())
        settings = self.call("PUT", "/api/settings", {"auto_images": False})[1]
        self.assertFalse(settings["auto_images"])
        self.assertFalse(ai.auto_images())
        self.assertFalse(self.call("GET", "/api/shopping")[1]["icons"]["enabled"])
        self.assertTrue(self.call("PUT", "/api/settings", {"auto_images": True})[1]["auto_images"])

    def test_claude_model_choice_shapes_the_request(self):
        settings = self.call("GET", "/api/settings")[1]
        self.assertEqual(settings["claude"]["model"], "claude-opus-5")
        self.assertEqual([m["name"] for m in settings["claude"]["models"]], ["Opus 5", "Sonnet 5", "Haiku 4.5"])
        self.assertEqual(self.call("PUT", "/api/settings", {"claude_model": "gpt-5"})[0], 400)

        def sent_options():
            fake = mock.MagicMock()
            stream = fake.beta.messages.stream.return_value.__enter__.return_value
            stream.get_final_message.return_value = mock.Mock(
                stop_reason="end_turn", content=[mock.Mock(type="text", text="{}")])
            with mock.patch.object(ai, "_client", return_value=(mock.Mock(), fake)):
                ai._ask_claude("systeem", "vraag", {"type": "object"}, "low")
            return fake.beta.messages.stream.call_args.kwargs

        opus = sent_options()
        self.assertEqual((opus["model"], opus["thinking"], opus["output_config"]["effort"], opus["fallbacks"]),
                         ("claude-opus-5", {"type": "adaptive"}, "low", "default"))
        self.call("PUT", "/api/settings", {"claude_model": "claude-sonnet-5"})
        sonnet = sent_options()
        self.assertEqual((sonnet["model"], sonnet["output_config"]["effort"]), ("claude-sonnet-5", "low"))
        self.assertNotIn("fallbacks", sonnet)
        self.call("PUT", "/api/settings", {"claude_model": "claude-haiku-4-5"})
        haiku = sent_options()
        self.assertEqual(haiku["model"], "claude-haiku-4-5")
        self.assertNotIn("thinking", haiku)
        self.assertNotIn("effort", haiku["output_config"])
        self.assertIn("format", haiku["output_config"])

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

    def test_ai_uses_key_from_settings(self):
        self.call("PUT", "/api/settings", {"claude_api_key": KEY})
        self.assertEqual(ai._setting(ai.CLAUDE_KEY), KEY)

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
