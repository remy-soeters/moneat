"""Boodschappen slim samenvoegen: hetzelfde product op één tegel, in een eenheid waarmee je kunt winkelen.

Recepten schrijven hetzelfde product op verschillende manieren ("tomatenblokjes uit blik 400 g", "1 blik
tomatenblokjes", "tomaten 2 stuks"). Hier maken we daar één product van, met een hoeveelheid die je in de
winkel pakt: blikken in plaats van grammen, hele uien in plaats van 0,5 stuk, en geen "1 el olijfolie".
"""

import math
import re
import unicodedata

# Hoeveelheden uit de keuken, niet uit de winkel: daarvan zet je alleen het product op de lijst.
KITCHEN_MEASURES = {"el", "tl", "snuf", "mespunt", "scheut", "handje", "handvol", "naar smaak", "takje", "cup", "kopje"}

# Eenheid → (basiseenheid, factor)
BASE_UNITS = {
    "g": ("g", 1), "gr": ("g", 1), "gram": ("g", 1), "kg": ("g", 1000), "kilo": ("g", 1000),
    "ml": ("ml", 1), "cl": ("ml", 10), "dl": ("ml", 100), "l": ("ml", 1000), "liter": ("ml", 1000),
    "": ("stuks", 1), "stuk": ("stuks", 1), "stuks": ("stuks", 1), "st": ("stuks", 1), "x": ("stuks", 1),
    "blik": ("blik", 1), "blikje": ("blik", 1), "blikken": ("blik", 1), "blikjes": ("blik", 1),
    "teen": ("teen", 1), "teentje": ("teen", 1), "teentjes": ("teen", 1), "tenen": ("teen", 1),
}

PLURALS = {
    "blik": "blikken", "teen": "tenen", "bos": "bossen", "zak": "zakken", "pak": "pakken", "plak": "plakken",
    "fles": "flessen", "pot": "potten", "net": "netten", "bak": "bakjes", "takje": "takjes",
}

# Producten die je in blik koopt, ook als het recept alleen grammen noemt; met de inhoud van één blik.
CANNED_GRAMS = {
    "tomatenblokjes": 400, "gepelde tomaten": 400, "gehakte tomaten": 400, "kokosmelk": 400, "kidneybonen": 400,
    "zwarte bonen": 400, "witte bonen": 400, "bruine bonen": 400, "borlottibonen": 400, "cannellinibonen": 400,
    "tomatenpuree": 70, "maïs": 285, "maïskorrels": 285, "jackfruit": 400, "kikkererwten": 400,
}
CAN_WORDS = re.compile(r"\s*(?:\((?:uit |in )?blik(?:je)?\)|\b(?:uit|in) (?:een )?blik(?:je)?\b|^blik(?:je)?\s+)\s*")

# Gewicht van één stuk, om grammen om te rekenen naar hele stuks.
PIECE_GRAMS = {
    "ui": 150, "rode ui": 150, "sjalot": 40, "tomaat": 120, "paprika": 170, "courgette": 250, "aubergine": 300,
    "wortel": 80, "citroen": 100, "limoen": 70, "sinaasappel": 150, "appel": 150, "aardappel": 150, "prei": 200,
    "komkommer": 350, "avocado": 170, "venkel": 250, "zoete aardappel": 300, "mango": 300, "banaan": 120,
    "ei": 55, "broccoli": 400, "bloemkool": 800, "knolselderij": 700, "pompoen": 1200,
}

# Onregelmatige meervouden (na het stammen).
IRREGULAR = {"eier": "ei", "kip": "kip"}

# Woorden die niets zeggen over wat je koopt.
FILLER = re.compile(r"\b(?:verse|vers|biologische|biologisch|bio|zelfgemaakte|zelfgemaakt|huisgemaakte|huisgemaakt)\b")
RECIPE_FILLER = re.compile(r"\b(?:snelle|makkelijke|simpele|eenvoudige|basis|recept|eigen|mijn|oma's)\b")


def display_name(name):
    """Naam voor op de tegel: zonder bereiding ("fijngesneden") en zonder "uit blik", met een hoofdletter."""
    text = str(name or "").strip()
    text = text.split(",")[0].strip() or text
    text = CAN_WORDS.sub(" ", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:1].upper() + text[1:]


def is_canned(name, unit=""):
    return bool(CAN_WORDS.search(str(name or "").lower())) or BASE_UNITS.get(str(unit or "").lower(), ("",))[0] == "blik"


def _plain(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _stem(word):
    """Enkelvoud en meervoud op één noemer: tomaten/tomaat → tomat, uien/ui → ui, bonen/boon → bon."""
    if word.endswith("'s"):
        word = word[:-2]
    elif word.endswith("en") and len(word) >= 4:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 4 and not word.endswith("ss"):
        word = word[:-1]
    word = re.sub(r"(aa|ee|oo|uu)([^aeiou]+)$", lambda m: m.group(1)[0] + m.group(2), word)
    return IRREGULAR.get(word, word)


def product_key(name):
    """Sleutel om gelijke producten samen te voegen."""
    text = _plain(display_name(name)).replace("\u2019", "'")
    text = re.sub(r"\(.*?\)", " ", text)
    text = FILLER.sub(" ", text)
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", text)
    if not words:
        return _plain(name).strip()
    return " ".join([*words[:-1], _stem(words[-1])])


CANNED = {product_key(name): grams for name, grams in CANNED_GRAMS.items()}
PIECES = {product_key(name): grams for name, grams in PIECE_GRAMS.items()}


def shopping_product(name, unit=""):
    """(sleutel, naam) van een regel op de boodschappenlijst. Iets uit blik is een ander product dan vers
    (tomaten ≠ tomaten uit blik), behalve bij wat je toch altijd in blik koopt (kidneybonen, kokosmelk)."""
    key = product_key(name)
    if key not in CANNED and is_canned(name, unit):
        # "1 blik" in de hoeveelheid zegt het al; alleen "tomaten uit blik" zonder hoeveelheid krijgt het in de naam
        said = CAN_WORDS.search(str(name or "").lower())
        return f"{key} blik", display_name(name) + (" (blik)" if said else "")
    return key, display_name(name)


def recipe_key(name):
    """Sleutel van een recept om te zien of een ingrediënt iets is wat je zelf maakt (zoals naan)."""
    return product_key(RECIPE_FILLER.sub(" ", _plain(name)))


def homemade_match(ingredient_name, recipes_by_key):
    """Het eigen recept voor dit ingrediënt, of None. "naanbrood" past ook bij het recept "Naan"."""
    key = product_key(ingredient_name)
    if key in recipes_by_key:
        return recipes_by_key[key]
    if key.endswith("brod") and len(key) > 6:  # "naanbrood" (gestemd: naanbrod) → naan
        return recipes_by_key.get(product_key(key[:-4]))
    return None


# ---------- hoeveelheden ----------


def combine(entries, key, canned=False):
    """Tel regels (quantity, unit) op tot {eenheid: hoeveelheid} om mee te winkelen."""
    totals = {}
    for quantity, unit in entries:
        unit = str(unit or "").strip().lower()
        if quantity is None or unit in KITCHEN_MEASURES:
            continue
        base, factor = BASE_UNITS.get(unit, (unit, 1))
        totals[base] = totals.get(base, 0) + quantity * factor
    size = CANNED.get(key) or (400 if canned else None)
    pieces = PIECES.get(key)
    if size:
        tins = totals.pop("blik", 0) + (totals.pop("g", 0) + totals.pop("ml", 0)) / size + totals.pop("stuks", 0)
        if tins:
            totals = {"blik": max(1, math.ceil(tins - 0.1)), **totals}
    else:
        if "stuks" in totals and "g" in totals and pieces:
            totals["stuks"] += totals.pop("g") / pieces
        if "g" in totals and "ml" in totals:  # bijv. passata in gram en in ml: dat is ongeveer hetzelfde
            big, small = ("g", "ml") if totals["g"] >= totals["ml"] else ("ml", "g")
            totals[big] += totals.pop(small)
    if "stuks" in totals:
        totals["stuks"] = max(1, math.ceil(totals["stuks"] - 0.05))  # je koopt hele stuks
    return {unit: amount for unit, amount in totals.items() if amount}


def _number(value):
    text = f"{round(value, 2):g}"
    return text.replace(".", ",")


def format_amount(totals):
    """{eenheid: hoeveelheid} → tekst, bijv. "2 blikken", "750 g", "1,5 kg" of "3"."""
    parts = []
    for unit, amount in totals.items():
        if unit == "g" and amount >= 1000:
            unit, amount = "kg", amount / 1000
        elif unit == "ml" and amount >= 1000:
            unit, amount = "l", amount / 1000
        elif unit in ("g", "ml") and amount >= 100:
            amount = round(amount / 5) * 5
        if unit == "stuks":
            parts.append(_number(amount))
        elif amount != 1 and unit in PLURALS:
            parts.append(f"{_number(amount)} {PLURALS[unit]}")
        else:
            parts.append(f"{_number(amount)} {unit}")
    return " + ".join(parts)


def primary(totals):
    """De eerste hoeveelheid als (quantity, unit), om het wijzigen mee te beginnen."""
    for unit, amount in totals.items():
        if unit == "g" and amount >= 1000:
            unit, amount = "kg", amount / 1000
        elif unit == "ml" and amount >= 1000:
            unit, amount = "l", amount / 1000
        return round(amount, 2), "" if unit == "stuks" else unit
    return None, ""
