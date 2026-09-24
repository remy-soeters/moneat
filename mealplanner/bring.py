"""Boodschappen automatisch naar Bring! sturen (alleen standaardbibliotheek).

Bring! heeft geen officiële API; dit gebruikt dezelfde REST-API als de Bring!-apps, zoals ook
de open-source bibliotheek `bring-api` (Home Assistant) doet.

Wat de sync doet, telkens als de lijst verandert en elke paar minuten:
- Wat hier onder *Kopen* staat, komt op de gekozen Bring!-lijst (met de hoeveelheid als toelichting).
- Vink je iets af in Bring!, of haal je het daar weg, dan staat het hier bij *Gekocht*.
- Koop je iets hier (of haal je het van de lijst), dan verdwijnt het ook uit Bring!.
Alleen producten die de app zelf naar Bring! stuurde worden aangeraakt; wat je in Bring! zelf
toevoegt blijft staan.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib

API_URL = "https://api.getbring.com/rest/"
LOCALES_URL = "https://web.getbring.com/locale/"
# Openbare sleutel van de Bring!-webapp: dezelfde voor iedereen (staat ook in open-source Bring!-clients),
# dus geen geheim.
API_KEY = "cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp"  # ggignore
DEFAULT_LOCALE = "nl-NL"
# In deze taal zijn de artikelnamen in Bring! zelf (Duits); daarvoor is geen vertaling nodig.
BASE_LOCALE = "de-CH"
TIMEOUT = 20
POLL_SECONDS = 120  # zo vaak kijken of er in Bring! iets is afgevinkt
DEBOUNCE_SECONDS = 1.5

EMAIL = "bring_email"
PASSWORD = "bring_password"
LIST_UUID = "bring_list_uuid"
LIST_NAME = "bring_list_name"


class BringError(Exception):
    pass


class BringAuthError(BringError):
    pass


class BringClient:
    """Een ingelogde sessie bij Bring!."""

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.user_uuid = None
        self.token = None
        self.expires_at = 0
        self.default_list = None
        self._translations = {}  # locale -> {nederlandse naam (klein): Bring!-artikel}

    def login(self):
        data = self._call("POST", "v2/bringauth", form={"email": self.email, "password": self.password}, auth=False)
        try:
            self.user_uuid = data["uuid"]
            self.token = f"{data.get('token_type') or 'Bearer'} {data['access_token']}"
        except (KeyError, TypeError):
            raise BringError("Onverwacht antwoord van Bring! bij het inloggen")
        self.expires_at = time.time() + int(data.get("expires_in") or 3600) - 60
        self.default_list = data.get("bringListUUID")
        return data

    def lists(self):
        self._ensure_login()
        data = self._call("GET", f"bringusers/{self.user_uuid}/lists")
        return [{"uuid": l["listUuid"], "name": l.get("name") or "Lijst"} for l in data.get("lists") or []]

    def items(self, list_uuid):
        """De producten die in Bring! nog gekocht moeten worden: [{itemId, specification, uuid}]."""
        data = self._call("GET", f"v2/bringlists/{list_uuid}")
        items = data.get("items") if isinstance(data.get("items"), dict) else data
        return [
            {"itemId": i.get("itemId") or i.get("name") or "", "specification": i.get("specification") or "", "uuid": i.get("uuid") or ""}
            for i in items.get("purchase") or []
        ]

    def update(self, list_uuid, changes):
        """Voer wijzigingen in één keer uit: [{itemId, spec, uuid, operation}] met operation
        TO_PURCHASE (op de lijst / toelichting bijwerken), TO_RECENTLY (afgevinkt) of REMOVE."""
        if not changes:
            return
        location = {"accuracy": "0.0", "altitude": "0.0", "latitude": "0.0", "longitude": "0.0"}
        self._call("PUT", f"v2/bringlists/{list_uuid}/items", body={
            "changes": [{**location, **change} for change in changes],
            "sender": "",
        })

    def list_locale(self, list_uuid):
        """De taal van de artikelen op deze lijst, bijv. 'nl-NL'."""
        self._ensure_login()
        try:
            data = self._call("GET", f"bringusersettings/{self.user_uuid}")
        except BringAuthError:
            raise
        except BringError:
            return DEFAULT_LOCALE
        for entry in data.get("userlistsettings") or []:
            if entry.get("listUuid") == list_uuid:
                for setting in entry.get("usersettings") or []:
                    if setting.get("key") == "listArticleLanguage" and setting.get("value"):
                        return setting["value"]
        return DEFAULT_LOCALE

    def article_names(self, locale):
        """{naam in de lijsttaal (klein): Bring!-artikel}, zodat 'Melk' in Bring! het artikel met icoon wordt.

        Lukt het ophalen niet, dan gaan producten als eigen artikel (zonder vertaling) naar Bring!.
        """
        if locale == BASE_LOCALE:
            return {}
        if locale not in self._translations:
            try:
                request = urllib.request.Request(f"{LOCALES_URL}articles.{urllib.parse.quote(locale)}.json")
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    articles = json.load(response)
                self._translations[locale] = {str(v).strip().lower(): k for k, v in articles.items()}
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, AttributeError):
                return {}
        return self._translations[locale]

    def _ensure_login(self):
        if self.token is None or time.time() > self.expires_at:
            self.login()

    def _call(self, method, path, form=None, body=None, auth=True, retry=True):
        if auth:
            self._ensure_login()
        headers = {
            "X-BRING-API-KEY": API_KEY,
            "X-BRING-CLIENT": "webApp",
            "X-BRING-APPLICATION": "bring",
            "X-BRING-COUNTRY": "NL",
        }
        if auth:
            headers["Authorization"] = self.token
            headers["X-BRING-USER-UUID"] = self.user_uuid
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(API_URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403) and not auth:
                raise BringAuthError("Bring! accepteert dit e-mailadres of wachtwoord niet")
            if e.code == 401 and retry:
                self.token = None  # verlopen: opnieuw inloggen en nog één keer proberen
                return self._call(method, path, form, body, auth, retry=False)
            if e.code == 401:
                raise BringAuthError("Bring! accepteert het wachtwoord niet meer; log opnieuw in bij Instellingen")
            raise BringError(f"Bring! gaf een fout ({e.code})")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BringError("Kon geen verbinding maken met Bring!. Controleer je internetverbinding.")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise BringError("Onverwacht antwoord van Bring!")


class BringSync:
    """Houdt de gekozen Bring!-lijst op de achtergrond gelijk met *Kopen*."""

    def __init__(self, db, client_factory=BringClient):
        self.db = db
        self.client_factory = client_factory
        self._client = None
        self._run_lock = threading.Lock()  # één sync tegelijk
        self._wake = threading.Event()
        self._thread = None
        self._thread_lock = threading.Lock()
        self.last_sync = None
        self.error = None

    # ---------- instellingen ----------

    def configured(self):
        return bool(self.db.get_setting(EMAIL) and self.db.get_setting(PASSWORD) and self.db.get_setting(LIST_UUID))

    def status(self):
        return {
            "connected": bool(self.db.get_setting(EMAIL) and self.db.get_setting(PASSWORD)),
            "email": self.db.get_setting(EMAIL),
            "list_uuid": self.db.get_setting(LIST_UUID),
            "list_name": self.db.get_setting(LIST_NAME),
            "last_sync": self.last_sync,
            "error": self.error,
            "synced": len(self.db.bring_synced()),
        }

    def connect(self, email, password):
        """Log in, bewaar de gegevens en kies de standaardlijst van Bring!. Geeft de lijsten terug."""
        email = str(email or "").strip()
        password = str(password or "")
        if "@" not in email or not password:
            raise ValueError("Vul je e-mailadres en wachtwoord van Bring! in")
        client = self.client_factory(email, password)
        client.login()
        lists = client.lists()
        if not lists:
            raise BringError("Je Bring!-account heeft nog geen lijst. Maak er eerst een aan in de app.")
        with self._run_lock:
            self._forget_synced()
            self._client = client
            self.db.set_setting(EMAIL, email)
            self.db.set_setting(PASSWORD, password)
            chosen = next((l for l in lists if l["uuid"] == client.default_list), lists[0])
            self.db.set_setting(LIST_UUID, chosen["uuid"])
            self.db.set_setting(LIST_NAME, chosen["name"])
            self.error = None
        self.kick()
        return lists

    def lists(self):
        with self._run_lock:
            return self._get_client().lists()

    def choose_list(self, list_uuid):
        with self._run_lock:
            chosen = next((l for l in self._get_client().lists() if l["uuid"] == list_uuid), None)
            if chosen is None:
                raise ValueError("Deze Bring!-lijst bestaat niet (meer)")
            if chosen["uuid"] != self.db.get_setting(LIST_UUID):
                self._take_back_items()  # niet laten slingeren op de vorige lijst
                self.db.set_setting(LIST_UUID, chosen["uuid"])
            self.db.set_setting(LIST_NAME, chosen["name"])
        self.kick()

    def disconnect(self):
        """Stop met synchroniseren. Wat al in Bring! staat blijft daar staan."""
        with self._run_lock:
            for key in (EMAIL, PASSWORD, LIST_UUID, LIST_NAME):
                self.db.set_setting(key, None)
            self._forget_synced()
            self._client = None
            self.error = None
            self.last_sync = None

    def _forget_synced(self):
        for key in self.db.bring_synced():
            self.db.delete_bring_item(key)

    def _take_back_items(self):
        """Haal wat de app op de huidige lijst zette er weer af (best effort)."""
        synced = self.db.bring_synced()
        try:
            self._get_client().update(self.db.get_setting(LIST_UUID), [
                {"itemId": row["item_id"], "spec": "", "uuid": row["uuid"], "operation": "REMOVE"} for row in synced.values()
            ])
        except BringError:
            pass
        self._forget_synced()

    def _get_client(self):
        if self._client is None:
            email, password = self.db.get_setting(EMAIL), self.db.get_setting(PASSWORD)
            if not (email and password):
                raise BringAuthError("Koppel eerst je Bring!-account bij Instellingen")
            self._client = self.client_factory(email, password)
        return self._client

    # ---------- synchroniseren ----------

    def sync(self):
        """Eén keer gelijktrekken. Geeft het aantal wijzigingen (beide kanten op) terug."""
        with self._run_lock:
            if not self.configured():
                return 0
            try:
                changed = self._sync()
            except BringError as e:
                self.error = str(e)
                raise
            self.error = None
            self.last_sync = time.strftime("%Y-%m-%dT%H:%M:%S")
            return changed

    def _sync(self):
        client = self._get_client()
        list_uuid = self.db.get_setting(LIST_UUID)
        remote = client.items(list_uuid)
        remote_uuids = {i["uuid"] for i in remote if i["uuid"]}
        remote_by_id = {i["itemId"].lower(): i for i in remote}
        synced = self.db.bring_synced()
        changed = 0

        # 1. In Bring! afgevinkt of weggehaald: hier als gekocht markeren.
        for key, row in list(synced.items()):
            if row["uuid"] not in remote_uuids and row["item_id"].lower() not in remote_by_id:
                if self.db.mark_product_bought(key):
                    changed += 1
                self.db.delete_bring_item(key)
                del synced[key]

        # 2. Wat hier gekocht moet worden naar Bring! sturen; wat niet meer hoeft eraf halen.
        wanted = self.db.bring_wanted()
        changes, save = [], []
        articles = None
        for key, item in wanted.items():
            row = synced.get(key)
            if row is None:
                if articles is None:
                    articles = client.article_names(client.list_locale(list_uuid))
                item_id = articles.get(item["name"].lower(), item["name"])
                existing = remote_by_id.get(item_id.lower())  # staat er al (zelf toegevoegd in Bring!)
                row = {"item_id": item_id, "uuid": existing["uuid"] if existing and existing["uuid"] else str(uuidlib.uuid4()), "spec": None}
            if row["spec"] != item["spec"]:
                changes.append({"itemId": row["item_id"], "spec": item["spec"], "uuid": row["uuid"], "operation": "TO_PURCHASE"})
                save.append((key, row["item_id"], row["uuid"], item["spec"]))
        gone = [key for key in synced if key not in wanted]
        for key in gone:
            row = synced[key]
            operation = "TO_RECENTLY" if self.db.product_bought(key) else "REMOVE"
            changes.append({"itemId": row["item_id"], "spec": row["spec"] or "", "uuid": row["uuid"], "operation": operation})

        client.update(list_uuid, changes)
        for key, item_id, item_uuid, spec in save:
            self.db.save_bring_item(key, item_id, item_uuid, spec)
        for key in gone:
            self.db.delete_bring_item(key)
        return changed + len(changes)

    # ---------- op de achtergrond ----------

    def kick(self):
        """Na een wijziging: over een ogenblik synchroniseren (wijzigingen vlak na elkaar gaan samen)."""
        if not self.configured():
            return
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="bring-sync", daemon=True)
                self._thread.start()
        self._wake.set()

    def _run(self):
        while self.configured():
            if self._wake.wait(POLL_SECONDS):
                time.sleep(DEBOUNCE_SECONDS)
            self._wake.clear()
            try:
                self.sync()
            except BringError:
                pass  # staat in self.error; volgende keer opnieuw
            except Exception as e:  # de achtergrondsync mag nooit stilletjes stoppen
                self.error = f"Synchroniseren met Bring! mislukte: {e}"
