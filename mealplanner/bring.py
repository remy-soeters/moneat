"""Koppeling met Bring! (boodschappen-app) via de onofficiële REST-API die ook Home Assistant gebruikt.

Bring! heeft geen openbare API; deze werkt zoals de Android-app. Het wachtwoord wordt alleen gebruikt om in
te loggen en niet bewaard: we bewaren de sleutels (tokens) die Bring! teruggeeft.
Bron voor de werking: https://github.com/miaucl/bring-api
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.getbring.com/rest"
LOCALES_URL = "https://web.getbring.com/locale"
LOCALE = "nl-NL"
TIMEOUT = 20
HEADERS = {
    "X-BRING-API-KEY": "cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp",  # vaste sleutel van de Bring!-app zelf
    "X-BRING-CLIENT": "android",
    "X-BRING-APPLICATION": "bring",
    "X-BRING-COUNTRY": "NL",
}

_catalog = None  # Nederlandse productnaam (kleine letters) -> Bring!-artikelcode, voor Bring!'s eigen plaatjes


class BringError(Exception):
    pass


def _call(method, path, auth=None, form=None, body=None):
    headers = dict(HEADERS)
    data = None
    if auth:
        headers["Authorization"] = f"Bearer {auth['access_token']}"
        headers["X-BRING-USER-UUID"] = auth["uuid"]
        headers["X-BRING-PUBLIC-USER-UUID"] = auth.get("public_uuid", "")
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}/{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise BringError("Bring! accepteert de inlog niet (meer). Koppel Bring! opnieuw bij Instellingen.") from None
        raise BringError(f"Bring! gaf een foutmelding ({e.code}). Probeer het later nog eens.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BringError("Kon geen verbinding maken met Bring!. Controleer je internetverbinding.") from None


def login(email, password):
    """Log in en geef de gegevens terug die we bewaren (zonder wachtwoord)."""
    if not email or not password:
        raise BringError("Vul je e-mailadres en wachtwoord van Bring! in.")
    try:
        data = _call("POST", "v2/bringauth", form={"email": email, "password": password})
    except BringError as e:
        if "accepteert" in str(e):
            raise BringError("E-mailadres of wachtwoord klopt niet.") from None
        raise
    return {
        "email": email,
        "uuid": data["uuid"],
        "public_uuid": data.get("publicUuid", ""),
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": time.time() + int(data.get("expires_in", 3600)),
        "list_uuid": data.get("bringListUUID", ""),
    }


def fresh(auth):
    """Vernieuw de toegang als die (bijna) verlopen is. Geeft True terug als `auth` is bijgewerkt."""
    if auth["expires_at"] - time.time() > 300:
        return False
    data = _call("POST", "v2/bringauth/token", form={"grant_type": "refresh_token", "refresh_token": auth["refresh_token"]})
    auth["access_token"] = data["access_token"]
    auth["refresh_token"] = data.get("refresh_token", auth["refresh_token"])
    auth["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    return True


def lists(auth):
    data = _call("GET", f"bringusers/{auth['uuid']}/lists", auth=auth)
    return [{"uuid": item["listUuid"], "name": item["name"]} for item in data.get("lists", [])]


def purchase_names(auth, list_uuid):
    """Namen (Bring!-codes) die nu op de koop-lijst in Bring! staan."""
    data = _call("GET", f"v2/bringlists/{list_uuid}", auth=auth)
    return {item["itemId"] for item in (data.get("items") or {}).get("purchase", [])}


def change(auth, list_uuid, changes):
    """changes: lijst van (naam, specificatie, 'TO_PURCHASE' | 'TO_RECENTLY')."""
    if not changes:
        return
    body = {
        "changes": [
            {"itemId": name, "spec": spec, "uuid": "", "operation": operation,
             "accuracy": "0.0", "altitude": "0.0", "latitude": "0.0", "longitude": "0.0"}
            for name, spec, operation in changes
        ],
        "sender": "",
    }
    _call("PUT", f"v2/bringlists/{list_uuid}/items", auth=auth, body=body)


def catalog_name(name):
    """Zet een productnaam om naar de code die Bring! kent (bijv. 'Tomaat' -> 'Tomaten'), zodat Bring!
    er zijn eigen plaatje bij toont. Onbekende producten blijven gewoon hun eigen naam houden."""
    global _catalog
    if _catalog is None:
        try:
            with urllib.request.urlopen(f"{LOCALES_URL}/articles.{LOCALE}.json", timeout=TIMEOUT) as response:
                articles = json.load(response)
            _catalog = {str(v).strip().lower(): k for k, v in articles.items() if isinstance(v, str)}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return name  # later opnieuw proberen
    word = name.strip().lower()
    # Bring! gebruikt vaak het meervoud: ui -> uien, tomaat -> tomaten, citroen -> citroenen.
    shortened = word[:-3] + word[-2:] if len(word) > 3 and word[-3] == word[-2] and word[-3] in "aeou" else word
    for guess in (word, word + "en", shortened + "en", word + "s", word + "n"):
        if guess in _catalog:
            return _catalog[guess]
    return name
