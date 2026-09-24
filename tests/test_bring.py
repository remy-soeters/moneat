import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from mealplanner import bring
from mealplanner.bring import BringAuthError, BringClient, BringSync
from mealplanner.db import Database
from mealplanner.server import make_handler

WEEK = "2026-09-21"


class FakeClient:
    """Bring! in het geheugen: één lijst met producten die gekocht moeten worden."""

    lists_ = [{"uuid": "list-1", "name": "Thuis"}, {"uuid": "list-2", "name": "Werk"}]

    def __init__(self, email, password):
        if password != "geheim":
            raise BringAuthError("Bring! accepteert dit e-mailadres of wachtwoord niet")
        self.default_list = "list-1"
        self.purchase = {"list-1": [], "list-2": []}
        self.recently = {"list-1": [], "list-2": []}
        self.calls = []

    def login(self):
        pass

    def lists(self):
        return self.lists_

    def items(self, list_uuid):
        return [dict(i) for i in self.purchase[list_uuid]]

    def update(self, list_uuid, changes):
        self.calls.append(changes)
        for change in changes:
            purchase = self.purchase[list_uuid]
            purchase[:] = [i for i in purchase if i["uuid"] != change["uuid"]]
            if change["operation"] == "TO_PURCHASE":
                purchase.append({"itemId": change["itemId"], "specification": change["spec"], "uuid": change["uuid"]})
            elif change["operation"] == "TO_RECENTLY":
                self.recently[list_uuid].append(change["itemId"])

    def list_locale(self, list_uuid):
        return "nl-NL"

    def article_names(self, locale):
        return {"melk": "Milch", "uien": "Zwiebeln"}

    def on_list(self, list_uuid="list-1"):
        return {i["itemId"]: i["specification"] for i in self.purchase[list_uuid]}


class BringSyncTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.clients = []

        def factory(email, password):
            client = FakeClient(email, password)
            self.clients.append(client)
            return client

        self.sync = BringSync(self.db, client_factory=factory)
        with mock.patch.object(self.sync, "kick"):
            self.sync.connect("ik@example.com", "geheim")
        self.bring = self.clients[-1]

    def test_connect_chooses_default_list_and_checks_password(self):
        status = self.sync.status()
        self.assertEqual((status["connected"], status["list_uuid"], status["list_name"]), (True, "list-1", "Thuis"))
        with self.assertRaises(BringAuthError):
            self.sync.connect("ik@example.com", "fout")
        with self.assertRaises(ValueError):
            self.sync.connect("", "")

    def test_pushes_to_buy_items_with_catalog_names_and_quantities(self):
        soup = self.db.create_recipe({"name": "Soep", "servings": 2, "ingredients": [
            {"name": "Uien", "quantity": 2, "unit": ""}, {"name": "Room", "quantity": 1.5, "unit": "dl"},
        ]})
        self.db.choose_dinner(WEEK, soup["id"])
        self.db.add_shopping_item("Melk", 1, "l")
        self.db.add_shopping_item("uien", 1)

        self.sync.sync()
        self.assertEqual(self.bring.on_list(), {"Zwiebeln": "3", "Room": "1,5 dl", "Milch": "1 l"})

        # Niets veranderd: geen nieuwe wijzigingen naar Bring!.
        calls = len(self.bring.calls)
        self.assertEqual(self.sync.sync(), 0)
        self.assertEqual(self.bring.calls[calls:], [[]])

        # Meer personen: de hoeveelheid in Bring! gaat mee.
        self.db.choose_dinner(WEEK, soup["id"], 4)
        self.sync.sync()
        self.assertEqual(self.bring.on_list()["Room"], "3 dl")

    def test_bought_or_removed_here_updates_bring(self):
        self.db.add_shopping_item("Melk", 1, "l")
        self.db.add_shopping_item("Kaas")
        self.sync.sync()
        self.db.set_shopping_check("buy:melk|l", True)
        self.db.remove_shopping_item("buy:kaas|")
        self.sync.sync()
        self.assertEqual(self.bring.on_list(), {})
        self.assertEqual(self.bring.recently["list-1"], ["Milch"])  # gekocht = afgevinkt, niet weg
        self.assertEqual(self.db.bring_synced(), {})

        # Terugzetten naar Kopen zet het weer op Bring!.
        self.db.set_shopping_check("bought:melk|l", False)
        self.sync.sync()
        self.assertEqual(self.bring.on_list(), {"Milch": "1 l"})

    def test_checked_off_in_bring_is_bought_here(self):
        self.db.add_shopping_item("Melk", 1, "l")
        self.db.add_shopping_item("Kaas")
        self.sync.sync()
        self.bring.update("list-1", [{"itemId": "Milch", "spec": "", "uuid": self.db.bring_synced()["melk"]["uuid"], "operation": "TO_RECENTLY"}])

        self.assertEqual(self.sync.sync(), 1)
        self.assertEqual({i["name"]: i["checked"] for i in self.db.shopping_list()}, {"Melk": True, "Kaas": False})
        self.assertEqual(self.bring.on_list(), {"Kaas": ""})  # niet opnieuw op Bring! gezet
        self.assertEqual(self.db.frequent_purchases()[0]["name"], "Melk")

    def test_leaves_own_bring_items_alone_and_reuses_existing(self):
        self.bring.purchase["list-1"] += [
            {"itemId": "Bier", "specification": "krat", "uuid": "eigen-1"},
            {"itemId": "Milch", "specification": "", "uuid": "eigen-2"},
        ]
        self.db.add_shopping_item("Melk", 2, "l")
        self.sync.sync()
        self.assertEqual(self.bring.on_list(), {"Bier": "krat", "Milch": "2 l"})  # geen dubbele melk
        self.assertEqual(self.db.bring_synced()["melk"]["uuid"], "eigen-2")

        self.db.set_shopping_check("buy:melk|l", True)
        self.sync.sync()
        self.assertEqual(self.bring.on_list(), {"Bier": "krat"})

    def test_switching_list_moves_items(self):
        self.db.add_shopping_item("Kaas")
        self.sync.sync()
        with mock.patch.object(self.sync, "kick"):
            self.sync.choose_list("list-2")
        self.sync.sync()
        self.assertEqual((self.bring.on_list("list-1"), self.bring.on_list("list-2")), ({}, {"Kaas": ""}))
        with self.assertRaises(ValueError):
            self.sync.choose_list("bestaat-niet")

    def test_disconnect_forgets_everything(self):
        self.db.add_shopping_item("Kaas")
        self.sync.sync()
        self.sync.disconnect()
        self.assertFalse(self.sync.status()["connected"])
        self.assertEqual(self.db.bring_synced(), {})
        self.assertIsNone(self.db.get_setting(bring.PASSWORD))
        self.assertEqual(self.sync.sync(), 0)  # niet gekoppeld: niets te doen


class BringApiTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.bring_sync = BringSync(self.db, client_factory=FakeClient)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db, bring=self.bring_sync))
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

    def test_connect_sync_and_disconnect(self):
        status, body = self.call("GET", "/api/bring")
        self.assertEqual((status, body["connected"]), (200, False))
        status, body = self.call("POST", "/api/bring/connect", {"email": "ik@example.com", "password": "fout"})
        self.assertEqual(status, 502)
        self.assertIn("wachtwoord", body["error"])

        with mock.patch.object(self.bring_sync, "kick") as kick:
            status, body = self.call("POST", "/api/bring/connect", {"email": "ik@example.com", "password": "geheim"})
            self.assertEqual((status, body["list_name"], len(body["lists"])), (200, "Thuis", 2))
            self.call("POST", "/api/shopping/items", {"text": "2 liter melk"})
            kick.assert_called()  # een wijziging in de lijst zet de sync in gang

        status, body = self.call("POST", "/api/bring/sync", {})
        self.assertEqual((status, body["changed"], body["bring"]["synced"]), (200, 1, 1))
        self.assertEqual(self.bring_sync._client.on_list(), {"Milch": "2 l"})

        status, body = self.call("PUT", "/api/bring/list", {"list_uuid": "list-2"})
        self.assertEqual((status, body["list_name"]), (200, "Werk"))

        status, body = self.call("DELETE", "/api/bring")
        self.assertEqual((status, body["connected"], body["email"]), (200, False, None))


class FakeBringServer(BaseHTTPRequestHandler):
    """Doet zich voor als api.getbring.com, om de HTTP-kant van BringClient te testen."""

    requests = []

    def log_message(self, *args):
        pass

    def _reply(self, status, payload=None):
        data = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode()
        self.requests.append((self.command, self.path, self.headers, body))
        if self.path == "/rest/v2/bringauth":
            form = urllib.parse.parse_qs(body)
            if form.get("password") != ["geheim"]:
                return self._reply(401, {"message": "wrong"})
            return self._reply(200, {"uuid": "user-1", "publicUuid": "p", "bringListUUID": "list-1",
                                     "access_token": "tok", "refresh_token": "r", "token_type": "Bearer", "expires_in": 3600})
        if self.headers.get("Authorization") != "Bearer tok":
            return self._reply(401, {"message": "token"})
        if self.path == "/rest/bringusers/user-1/lists":
            return self._reply(200, {"lists": [{"listUuid": "list-1", "name": "Thuis", "theme": "x"}]})
        if self.path == "/rest/v2/bringlists/list-1":
            return self._reply(200, {"uuid": "list-1", "status": "SHARED", "items": {
                "purchase": [{"uuid": "a", "itemId": "Milch", "specification": "1 l", "attributes": []}], "recently": []}})
        if self.path == "/rest/v2/bringlists/list-1/items":
            return self._reply(204)
        if self.path == "/rest/bringusersettings/user-1":
            return self._reply(200, {"usersettings": [], "userlistsettings": [
                {"listUuid": "list-1", "usersettings": [{"key": "listArticleLanguage", "value": "nl-NL"}]}]})
        self._reply(404, {})

    do_GET = do_POST = do_PUT = _handle


class BringClientHttpTest(unittest.TestCase):
    def setUp(self):
        FakeBringServer.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBringServer)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        patcher = mock.patch.object(bring, "API_URL", f"http://127.0.0.1:{self.server.server_address[1]}/rest/")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_login_lists_items_and_update(self):
        client = BringClient("ik@example.com", "geheim")
        self.assertEqual(client.lists(), [{"uuid": "list-1", "name": "Thuis"}])  # logt zelf in
        self.assertEqual(client.default_list, "list-1")
        self.assertEqual(client.items("list-1"), [{"itemId": "Milch", "specification": "1 l", "uuid": "a"}])
        self.assertEqual(client.list_locale("list-1"), "nl-NL")
        client.update("list-1", [{"itemId": "Milch", "spec": "", "uuid": "a", "operation": "REMOVE"}])

        method, path, headers, body = FakeBringServer.requests[-1]
        self.assertEqual((method, path, headers["X-BRING-USER-UUID"]), ("PUT", "/rest/v2/bringlists/list-1/items", "user-1"))
        self.assertEqual(headers["X-BRING-API-KEY"], bring.API_KEY)
        change = json.loads(body)["changes"][0]
        self.assertEqual((change["itemId"], change["operation"], change["uuid"]), ("Milch", "REMOVE", "a"))

    def test_expired_token_logs_in_again(self):
        client = BringClient("ik@example.com", "geheim")
        client.login()
        client.token = "Bearer verlopen"
        self.assertEqual(len(client.lists()), 1)
        logins = [r for r in FakeBringServer.requests if r[1] == "/rest/v2/bringauth"]
        self.assertEqual(len(logins), 2)

    def test_wrong_password(self):
        with self.assertRaises(BringAuthError):
            BringClient("ik@example.com", "fout").login()


if __name__ == "__main__":
    unittest.main()
