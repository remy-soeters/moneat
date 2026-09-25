"""Recepten importeren van een website.

Vrijwel alle receptensites publiceren hun recept als schema.org/Recipe in een
<script type="application/ld+json">-blok (dat is wat Google gebruikt voor receptkaarten).
Dat lezen we hier uit. Lukt dat niet, dan geeft `fetch_page` de leesbare tekst terug
zodat Claude het recept eruit kan halen.
"""

import html
import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import netguard

MAX_PAGE_BYTES = 5_000_000
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

UNITS = {
    "g": "g", "gr": "g", "gram": "g", "grams": "g", "kg": "kg", "kilo": "kg",
    "ml": "ml", "cl": "cl", "dl": "dl", "l": "l", "liter": "l",
    "el": "el", "eetlepel": "el", "eetlepels": "el", "tbsp": "el", "tablespoon": "el", "tablespoons": "el",
    "tl": "tl", "theelepel": "tl", "theelepels": "tl", "tsp": "tl", "teaspoon": "tl", "teaspoons": "tl",
    "stuk": "stuks", "stuks": "stuks", "st": "stuks",
    "teen": "teen", "teentje": "teen", "teentjes": "teen", "tenen": "teen",
    "blik": "blik", "blikje": "blik", "blikken": "blik", "pak": "pak", "pakje": "pak", "zak": "zak", "zakje": "zak",
    "bos": "bos", "bosje": "bos", "takje": "takje", "takjes": "takje", "plak": "plak", "plakken": "plak",
    "snuf": "snuf", "snufje": "snuf", "mespunt": "mespunt", "scheut": "scheut", "handje": "handje", "handvol": "handvol",
    "cup": "cup", "cups": "cup", "kopje": "kopje", "kop": "kopje",
}
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}
QUANTITY = re.compile(
    r"^\s*(?:(?P<slash>\d+/\d+)|(?P<num>\d+(?:[.,]\d+)?)?\s*(?P<frac>[½¼¾⅓⅔⅛]|\d+/\d+)?)"
    r"(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*(?P<rest>.*)$"
)


class ImportFailed(Exception):
    pass


# ---------- pagina ophalen ----------


def fetch(url, max_bytes=MAX_PAGE_BYTES):
    """Haal een URL op; geeft (bytes, content_type, uiteindelijke url)."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ImportFailed("Alleen http- en https-links worden ondersteund")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "nl,en;q=0.8"})
    try:
        with netguard.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ImportFailed("De pagina is te groot om te importeren")
            return data, response.headers.get("Content-Type", ""), response.geturl()
    except urllib.error.HTTPError as e:
        raise ImportFailed(f"De website gaf een foutmelding ({e.code})")
    except netguard.BlockedAddress:
        raise ImportFailed("Alleen openbare websites kunnen worden geïmporteerd, geen adressen op je eigen netwerk")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ImportFailed("De website is niet bereikbaar. Controleer de link.")


def fetch_page(url):
    """Geeft (html-tekst, uiteindelijke url)."""
    data, content_type, final_url = fetch(url)
    charset = re.search(r"charset=([\w-]+)", content_type or "")
    return data.decode(charset.group(1) if charset else "utf-8", errors="replace"), final_url


# ---------- HTML ontleden ----------


class _PageParser(HTMLParser):
    """Verzamelt JSON-LD-blokken, og:-metadata en de leesbare tekst van een pagina."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.json_ld = []
        self.meta = {}
        self.text = []
        self._in_json_ld = False
        self._buffer = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and (attrs.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._buffer = []
        elif tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key and attrs.get("content"):
                self.meta.setdefault(key.lower(), attrs["content"])
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "div", "br", "tr"}:
            self.text.append("\n")

    def handle_data(self, data):
        if self._in_json_ld:
            self._buffer.append(data)
        elif not self._skip_depth:
            self.text.append(data)


def parse_page(page_html):
    parser = _PageParser()
    parser.feed(page_html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return parser.json_ld, parser.meta, text


def find_recipe_json(blocks):
    """Zoek het eerste schema.org Recipe-object in de JSON-LD-blokken."""

    def walk(node):
        if isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "Recipe" in kinds:
                return node
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in node:
                    found = walk(node[key])
                    if found:
                        return found
        return None

    for block in blocks:
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            # Sommige sites zetten ongeldige tekens in hun JSON; probeer het zonder regeleinden.
            try:
                data = json.loads(re.sub(r"[\r\n\t]+", " ", block.strip()))
            except json.JSONDecodeError:
                continue
        found = walk(data)
        if found:
            return found
    return None


# ---------- schema.org Recipe omzetten ----------


def _text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_text(v) for v in value if v)
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("text"))
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value))).strip()


def parse_duration(value):
    """ISO 8601-duur (PT1H30M) naar minuten."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?", str(value or "").strip(), re.I)
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g or 0) for g in match.groups())
    total = days * 1440 + hours * 60 + minutes
    return total or None


def parse_servings(value):
    for item in value if isinstance(value, list) else [value]:
        match = re.search(r"\d+", str(item or ""))
        if match:
            return int(match.group())
    return None


def parse_ingredient(line):
    """'200 g spaghetti' -> {quantity: 200, unit: 'g', name: 'spaghetti'}."""
    line = re.sub(r"\s+", " ", _text(line)).strip()
    match = QUANTITY.match(line)
    quantity = None
    rest = line
    if match and (match.group("num") or match.group("frac") or match.group("slash")):
        quantity = 0.0
        if match.group("num"):
            quantity += float(match.group("num").replace(",", "."))
        frac = match.group("frac") or match.group("slash")
        if frac:
            if "/" in frac:
                top, bottom = frac.split("/")
                quantity += int(top) / int(bottom) if int(bottom) else 0
            else:
                quantity += FRACTIONS[frac]
        quantity = round(quantity, 3)
        rest = match.group("rest")

    unit = ""
    if quantity is not None:
        first, _, remainder = rest.partition(" ")
        key = first.lower().rstrip(".")
        if key in UNITS and remainder:
            unit, rest = UNITS[key], remainder
    return {"name": rest.strip(" ,") or line, "quantity": quantity, "unit": unit}


def parse_instructions(value):
    steps = []

    def walk(node):
        if isinstance(node, str):
            for line in re.split(r"\n+", _text(node)):
                if line.strip():
                    steps.append(line.strip())
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "itemListElement" in node:  # HowToSection
                walk(node["itemListElement"])
            else:
                walk(node.get("text") or node.get("name") or "")

    walk(value)
    steps = [re.sub(r"^\s*(stap\s*)?\d+[.):]?\s+", "", s, flags=re.I) for s in steps]
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def image_url(value, base):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return urljoin(base, value) if isinstance(value, str) and value.strip() else None


def clean_tags(data):
    """Tags uit categorie, keuken en trefwoorden, zonder ruis als 'recepten' of de naam van de auteur."""
    authors = {_text(a).lower() for a in (data.get("author") if isinstance(data.get("author"), list) else [data.get("author")])}
    tags = []
    for key in ("recipeCategory", "recipeCuisine", "keywords"):
        for tag in re.split(r"\s*,\s*", _text(data.get(key))):
            tag = re.sub(r"(recepten|recept|recipes|recipe)\b", " ", tag.lower()).strip()
            if tag and tag not in tags and tag not in authors and len(tag) <= 30:
                tags.append(tag)
    return tags


def recipe_from_schema(data, base_url):
    tags = clean_tags(data)
    minutes = parse_duration(data.get("totalTime")) or (
        (parse_duration(data.get("prepTime")) or 0) + (parse_duration(data.get("cookTime")) or 0) or None
    )
    return {
        "name": _text(data.get("name")),
        "servings": parse_servings(data.get("recipeYield")) or 2,
        "prep_minutes": minutes,
        "tags": ", ".join(tags[:5]),
        "instructions": parse_instructions(data.get("recipeInstructions")),
        "ingredients": [parse_ingredient(i) for i in data.get("recipeIngredient") or [] if _text(i)],
        "image_url": image_url(data.get("image"), base_url),
    }


# ---------- samenvoegen ----------


def import_recipe(url, image_store, ai_extract=None):
    """Haal een recept van `url` op als concept (nog niet opgeslagen).

    ai_extract(page_text, url) wordt gebruikt als de pagina geen gestructureerd recept bevat.
    """
    page, final_url = fetch_page(url)
    blocks, meta, text = parse_page(page)
    schema = find_recipe_json(blocks)

    if schema:
        recipe = recipe_from_schema(schema, final_url)
    elif ai_extract is not None:
        recipe = ai_extract(text[:60_000], final_url)
        recipe["image_url"] = None
    else:
        raise ImportFailed("Op deze pagina staat geen recept dat ik kan lezen")

    if not recipe.get("name"):
        recipe["name"] = _text(meta.get("og:title")) or "Geïmporteerd recept"

    image = recipe.pop("image_url", None) or image_url(meta.get("og:image"), final_url)
    recipe["image"] = ""
    if image:
        try:
            data, _, _ = fetch(image, max_bytes=8_000_000)
            recipe["image"] = image_store.save(data)
        except (ImportFailed, ValueError):
            pass  # Zonder foto is het recept nog steeds bruikbaar.
    recipe["source_url"] = final_url
    return recipe
