"""Alle AI in de app: menu-opties, recepten bedenken, uitschrijven en uitlezen, inspiratie (Claude of Gemini) en foto's
(Gemini)."""

import importlib.util
import json
import os
import threading
from contextlib import contextmanager

from . import gemini
from .setting_keys import (
    AUTO_IMAGES, CLAUDE_KEY, CLAUDE_MODEL, GEMINI_IMAGE_MODEL, GEMINI_KEY, GEMINI_TEXT_KEY, GEMINI_TEXT_MODEL,
    TEXT_PROVIDER,
)

MODEL = "claude-opus-5"  # standaard Claude-model
# Keuzes in Instellingen. Haiku kan niet 'nadenken' (adaptive thinking) en kent geen effort-niveau;
# de server-side fallback bij een weigering is er alleen voor Opus 5.
CLAUDE_MODELS = [
    {"id": "claude-opus-5", "name": "Opus 5", "note": "Beste kwaliteit, duurst", "thinking": True, "fallback": True},
    {"id": "claude-sonnet-5", "name": "Sonnet 5", "note": "Bijna even goed, sneller en goedkoper", "thinking": True, "fallback": False},
    {"id": "claude-haiku-4-5", "name": "Haiku 4.5", "note": "Snelst en goedkoopst, eenvoudiger recepten", "thinking": False, "fallback": False},
]


class AIUnavailable(Exception):
    """De AI-functie kan niet draaien (SDK of API-sleutel ontbreekt, of de AI weigerde). `source` zegt welke AI het
    was en `detail` wat die precies antwoordde; beide komen in het logboek bij Instellingen → Foutmeldingen."""

    def __init__(self, message, detail="", source=""):
        super().__init__(message)
        self.detail = detail
        self.source = source


NO_KEY = "Er is nog geen Anthropic API-sleutel ingesteld. Voeg er een toe via Instellingen in het menu."


INGREDIENT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "quantity": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "unit": {"type": "string"},
    },
    "required": ["name", "quantity", "unit"],
    "additionalProperties": False,
}

NEW_RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "servings": {"type": "integer"},
        "prep_minutes": {"type": "integer"},
        "tags": {"type": "string"},
        "instructions": {"type": "string"},
        "ingredients": {"type": "array", "items": INGREDIENT_SCHEMA},
    },
    "required": ["name", "servings", "prep_minutes", "tags", "instructions", "ingredients"],
    "additionalProperties": False,
}

SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "existing_recipe_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "new_recipe": {"anyOf": [NEW_RECIPE_SCHEMA, {"type": "null"}]},
                    "reason": {"type": "string"},
                },
                "required": ["date", "existing_recipe_id", "new_recipe", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

INSPIRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"description": {"type": "string"}, "recipe": NEW_RECIPE_SCHEMA},
                "required": ["description", "recipe"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intro", "ideas"],
    "additionalProperties": False,
}

SWIPE_SCHEMA = {
    "type": "object",
    "properties": {"ideas": INSPIRATION_SCHEMA["properties"]["ideas"]},
    "required": ["ideas"],
    "additionalProperties": False,
}

RECIPE_RULES = """Recepten: Nederlandse namen, ingrediënten in metrische eenheden (g, ml, el, tl, teen, blik)
met hoeveelheden voor het opgegeven aantal personen; laat de eenheid leeg bij hele stuks (2 uien, 1 citroen)
en schrijf producten uit blik als "tomatenblokjes" met eenheid "blik". Tags als korte kommagescheiden woorden
(bijv. "vegetarisch, pasta, snel"), en een bereiding met één genummerde stap per regel.
De ingrediënten en de bereiding horen bij elkaar: elk ingrediënt uit de lijst wordt in een stap gebruikt, en alles
wat de bereiding gebruikt staat in de lijst (ook olie, boter, zout en peper)."""

# Voor één recept tegelijk (laten bedenken, zelf omschrijven, uitschrijven): volledig, zodat je er echt mee kunt koken.
DETAIL_RULES = """Schrijf het recept volledig uit, zodat iemand die het gerecht nog nooit gemaakt heeft het zonder vragen
kan koken:
- Begin met de voorbereiding: oven voorverwarmen, water aan de kook brengen, groenten wassen en snijden (en hoe:
  in blokjes van 1 cm, in dunne ringen, fijngehakt).
- Noem in elke stap welke ingrediënten erbij gaan en hoeveel, de vuurstand of oventemperatuur, hoe lang, en waaraan
  je ziet dat het goed is (glazig, goudbruin, gaar, ingedikt).
- Sla niets over: ook op smaak brengen, laten rusten, afgieten en opdienen met eventuele garnering.
- Meestal 7 tot 12 stappen van één tot drie zinnen.
- Het recept is af: alles wat op het bord komt, dus ook een bijgerecht als rijst, aardappelen, brood of salade als
  het gerecht dat nodig heeft (met ingrediënten en stappen).
Loop het recept aan het eind na: wordt elk ingrediënt gebruikt, staat alles wat je gebruikt in de lijst, kloppen
de hoeveelheden bij het aantal personen, en klopt prep_minutes (de totale tijd, inclusief oven- en wachttijd)?"""

MENU_SYSTEM = f"""Je bent een praktische maaltijdplanner voor een Nederlands huishouden.
Je stelt keuze-opties voor het avondeten samen: per gevraagde datum een paar verschillende gerechten,
waaruit het huishouden er later één kiest. Hergebruik bestaande recepten waar ze passen (zet dan
existing_recipe_id en laat new_recipe null). Stel een nieuw recept voor wanneer dat het menu
gevarieerder maakt of beter bij de wensen past (zet dan new_recipe en laat existing_recipe_id null).
Maak de opties op één dag duidelijk verschillend (bijv. vlees, vis, vegetarisch of snel versus uitgebreid),
en zorg voor afwisseling over de week. Elk gerecht komt maar één keer in de week voor: stel niets voor wat al
op het menu van deze week staat (op welke dag dan ook), en geef hetzelfde gerecht nooit op twee datums.
Gerechten die deze week al afgewezen of niet gekozen zijn, stel je deze week niet opnieuw voor (ook niet een
variant ervan). Wat recent gegeten is, liever nog niet opnieuw, tenzij het een favoriet is.
Kies bestaande recepten met "favoriet": true of een hoge "beoordeling" (4 of 5 sterren) vaker; recepten met een
beoordeling van 2 of lager liever niet, en stel dan ook geen vergelijkbaar nieuw gerecht voor.
{RECIPE_RULES}
Geef per optie in één zin waarom hij op het menu staat."""

GENERATE_SYSTEM = f"""Je bent een ervaren thuiskok die betrouwbare recepten schrijft voor een Nederlands huishouden.
Schrijf precies het gevraagde gerecht, met ingrediënten die in een gewone Nederlandse supermarkt te krijgen zijn.
{RECIPE_RULES}
{DETAIL_RULES}"""

WRITE_OUT_SYSTEM = f"""Je bent een ervaren thuiskok en receptenredacteur voor een Nederlands huishouden. Je krijgt een
kort recept (een schets) en schrijft het volledig uit. Houd het hetzelfde gerecht: dezelfde naam, hetzelfde aantal
personen en dezelfde hoofdingrediënten. Vul aan wat ontbreekt en verbeter wat niet klopt, zoals ingrediënten die
nergens gebruikt worden, stappen met ingrediënten die niet in de lijst staan, of een recept dat halverwege ophoudt.
{RECIPE_RULES}
{DETAIL_RULES}"""

EXTRACT_SYSTEM = f"""Je haalt een recept uit de tekst van een webpagina. Neem het recept zo getrouw mogelijk over;
verzin geen ingrediënten of stappen die er niet staan. Vertaal naar het Nederlands als de pagina in een andere
taal is en reken imperiale eenheden om naar metrische. Staat er geen recept op de pagina, geef dan als naam
"GEEN RECEPT" en laat de lijsten leeg.
{RECIPE_RULES}"""

INSPIRATION_SYSTEM = f"""Je bent de redacteur van een Nederlandse receptenwebsite en stelt inspirerende collecties samen.
Kies gevarieerde, smakelijke avondgerechten die thuis goed te maken zijn. Schrijf een korte, uitnodigende
intro (twee zinnen) en per recept één aantrekkelijke zin die laat zien waarom het de moeite waard is.
{RECIPE_RULES}"""


# Leest een instelling van de app: get(key, default). Ingesteld door de server.
_setting = lambda key, default=None: default


def set_settings(getter):
    global _setting
    _setting = getter


# ---------- verbruik: elk verzoek dat iets maakt, voor het overzicht bij Instellingen → Foto's en iconen ----------

_record = lambda entry: None  # ingesteld door de server (Database.log_ai_usage)
_usage_context = threading.local()


def set_usage_recorder(record):
    global _record
    _record = record


@contextmanager
def usage(purpose, auto=False):
    """Waarvoor de AI-verzoeken in dit blok zijn, en of de app ze vanzelf doet (op de achtergrond) in plaats van
    omdat iemand erom vroeg. Zonder dit blok geldt het doel dat de functie zelf noemt."""
    previous = getattr(_usage_context, "value", None)
    _usage_context.value = (purpose, auto)
    try:
        yield
    finally:
        _usage_context.value = previous


def _log_usage(kind, provider, model, purpose, free=False, cost=None):
    purpose, auto = getattr(_usage_context, "value", None) or (purpose, False)
    try:
        _record({"kind": kind, "purpose": purpose, "auto": auto, "provider": provider, "model": model,
                 "free": free, "cost": cost})
    except Exception:
        pass  # het overzicht mag de AI zelf nooit in de weg zitten


def image_cost(model):
    """Geschatte prijs van één foto of icoon met dit model (in dollars), of None als we die niet kennen."""
    return next((m["cost"] for m in gemini.IMAGE_MODELS if m["id"] == model), None)


def text_provider():
    return _setting(TEXT_PROVIDER, "claude")


def provider_name():
    return "Gemini" if text_provider() == "gemini" else "Claude"


def claude_model():
    chosen = _setting(CLAUDE_MODEL)
    return next((m for m in CLAUDE_MODELS if m["id"] == chosen), CLAUDE_MODELS[0])


def gemini_models():
    return (
        _setting(GEMINI_TEXT_MODEL) or gemini.DEFAULT_TEXT_MODEL,
        _setting(GEMINI_IMAGE_MODEL) or gemini.DEFAULT_IMAGE_MODEL,
    )


def gemini_configured():
    return bool(_gemini_key(required=False))


def auto_images():
    """Mag de app zelf (op de achtergrond) foto's en iconen laten maken? Handmatig kan altijd."""
    return _setting(AUTO_IMAGES) != "off" and gemini_configured()


def _gemini_key(required=True):
    """De gewone Gemini-sleutel (ook voor foto's): uit de app, anders uit de omgeving."""
    key = _setting(GEMINI_KEY) or os.environ.get("GEMINI_API_KEY")
    if not key and required:
        raise AIUnavailable(
            "Er is nog geen Gemini API-sleutel ingesteld. Voeg er een toe via Instellingen in het menu.", source="Gemini"
        )
    return key


def _gemini_text_key():
    """Voor tekst gaat de gratis sleutel voor (als die er is); anders de gewone."""
    return _setting(GEMINI_TEXT_KEY) or _gemini_key()


def sdk_installed():
    return importlib.util.find_spec("anthropic") is not None


def env_key_present():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _client():
    try:
        import anthropic
    except ImportError:
        raise AIUnavailable(
            "Het pakket 'anthropic' is niet geïnstalleerd. Kijk bij Instellingen in het menu hoe je dat oplost.",
            source="Claude",
        )
    key = _setting(CLAUDE_KEY)
    try:
        # Een sleutel uit de app gaat voor; anders zoekt de SDK zelf (omgevingsvariabele of `ant auth login`).
        return anthropic, anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError as e:
        raise AIUnavailable(NO_KEY, repr(e), "Claude")


def _from_gemini(error):
    return AIUnavailable(str(error), error.detail, "Gemini")


def _claude_detail(error):
    """Precies wat de Claude API antwoordde, voor het logboek."""
    body = json.dumps(error.body, ensure_ascii=False) if getattr(error, "body", None) else error.message
    return f"HTTP {error.status_code} (request-id {getattr(error, 'request_id', None) or '?'}): {body}"


def _claude_error(error):
    """Een duidelijke melding bij een API-fout van Claude (bijv. tegoed op of te druk)."""
    text = str(error.message).lower()
    if "credit balance" in text:
        message = "Je Claude-tegoed is op. Vul het aan op console.anthropic.com (Plans & Billing) en probeer het opnieuw."
    elif error.status_code == 529 or "overloaded" in text:
        message = "Claude heeft het even te druk. Probeer het over een paar minuten opnieuw."
    else:
        message = f"Claude API-fout ({error.status_code}): {error.message}"
    return AIUnavailable(message, _claude_detail(error), "Claude")


def check_gemini():
    """Controleer de Gemini-sleutel en modellen, zonder iets te genereren."""
    try:
        text_model, image_model = gemini_models()
        if _setting(GEMINI_TEXT_KEY):
            gemini.check_connection(_setting(GEMINI_TEXT_KEY), [text_model])
            if _gemini_key(required=False):
                gemini.check_connection(_gemini_key(), [image_model])
        else:
            gemini.check_connection(_gemini_key(), [text_model, image_model])
    except gemini.GeminiError as e:
        raise _from_gemini(e)


def check_connection():
    """Controleer of Claude bereikbaar is met de huidige sleutel, zonder tokens te verbruiken."""
    anthropic, client = _client()
    try:
        client.models.retrieve(claude_model()["id"])
    except anthropic.AuthenticationError as e:
        raise AIUnavailable("Deze API-sleutel wordt niet geaccepteerd. Controleer of je hem volledig hebt geplakt.",
                            _claude_detail(e), "Claude")
    except anthropic.PermissionDeniedError as e:
        raise AIUnavailable("Deze API-sleutel heeft geen toegang tot Claude. Controleer je account op console.anthropic.com.",
                            _claude_detail(e), "Claude")
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("De server kon Claude niet bereiken. Is de internetverbinding van de server in orde?",
                            repr(e), "Claude")
    except anthropic.APIStatusError as e:
        raise _claude_error(e)
    except anthropic.AnthropicError as e:
        raise AIUnavailable(NO_KEY, repr(e), "Claude")
    except TypeError as e:
        _raise_if_no_key(e)


def _raise_if_no_key(error):
    """Zonder sleutel geeft de SDK pas bij het versturen een TypeError; maak daar een duidelijke melding van."""
    if "authentication" in str(error).lower():
        raise AIUnavailable(NO_KEY, repr(error), "Claude")
    raise error


def _ask(system, user_message, schema, effort="medium", purpose="Tekst"):
    """Stel de gekozen AI een vraag en krijg JSON terug volgens `schema`."""
    if text_provider() == "gemini":
        model = gemini_models()[0]
        try:
            result = gemini.generate_json(_gemini_text_key(), model, system, user_message, schema)
        except gemini.GeminiError as e:
            raise _from_gemini(e)
        _log_usage("tekst", "Gemini", model, purpose, free=bool(_setting(GEMINI_TEXT_KEY)))
        return result
    result = _ask_claude(system, user_message, schema, effort)
    _log_usage("tekst", "Claude", claude_model()["id"], purpose)
    return result


def _ask_claude(system, user_message, schema, effort):
    """Stel Claude een vraag en krijg JSON terug volgens `schema`."""
    anthropic, client = _client()
    try:
        # Streaming, omdat een volle week of een collectie recepten een lang antwoord kan opleveren.
        model = claude_model()
        options = {"output_config": {"format": {"type": "json_schema", "schema": schema}}}
        if model["thinking"]:
            options["thinking"] = {"type": "adaptive"}
            options["output_config"]["effort"] = effort
        if model["fallback"]:
            options.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        with client.beta.messages.stream(
            model=model["id"],
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            **options,
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise AIUnavailable("De API-sleutel wordt niet geaccepteerd. Controleer hem bij Instellingen in het menu.",
                            _claude_detail(e), "Claude")
    except anthropic.RateLimitError as e:
        raise AIUnavailable("Te veel verzoeken aan Claude; probeer het over een minuut opnieuw.",
                            _claude_detail(e), "Claude")
    except anthropic.APIStatusError as e:
        raise _claude_error(e)
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("De server kon Claude niet bereiken. Is de internetverbinding van de server in orde?",
                            repr(e), "Claude")
    except anthropic.AnthropicError as e:
        # Bijvoorbeeld: geen API-sleutel of profiel gevonden.
        raise AIUnavailable(NO_KEY, repr(e), "Claude")
    except TypeError as e:
        _raise_if_no_key(e)

    if response.stop_reason == "refusal":
        raise AIUnavailable("Claude kon dit verzoek niet uitvoeren. Formuleer het anders en probeer het opnieuw.",
                            "stop_reason: refusal", "Claude")
    if response.stop_reason == "max_tokens":
        raise AIUnavailable("Het antwoord van Claude was te lang en is afgebroken; vraag om minder tegelijk.",
                            "stop_reason: max_tokens", "Claude")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def suggest_menu_options(recipes, needs, current_menu, wishes="", servings=2, avoid=(), recent=()):
    """Vraag Claude om opties voor het avondeten.

    needs: {datum: aantal opties dat er voor die avond bij moet}
    recipes: bestaande recepten (dicts met id, name, tags, prep_minutes)
    current_menu: opties die al op het menu staan (om dubbelingen te voorkomen)
    avoid: gerechten die deze week afgewezen of niet gekozen zijn, die niet terug moeten komen
    recent: wat de afgelopen weken gegeten is
    """
    known_ids = {r["id"] for r in recipes}
    catalog = []
    for r in recipes:
        item = {"id": r["id"], "name": r["name"], "tags": r["tags"], "prep_minutes": r["prep_minutes"]}
        if r.get("favorite"):
            item["favoriet"] = True
        if r.get("rating") is not None:
            item["beoordeling"] = r["rating"]
        catalog.append(item)
    wanted = "\n".join(f"- {day}: {count} optie(s)" for day, count in needs.items())
    suggestions = _ask(
        MENU_SYSTEM,
        f"Stel opties voor het avondeten voor. Aantal nieuwe opties per datum:\n{wanted}\n\n"
        f"Aantal personen: {servings}.\n"
        f"Wensen: {wishes.strip() or 'geen bijzondere wensen'}.\n\n"
        f"Staat al op het menu:\n{json.dumps(current_menu, ensure_ascii=False)}\n\n"
        + (f"Deze week afgewezen of niet gekozen, stel deze en vergelijkbare gerechten niet voor: {json.dumps(list(avoid), ensure_ascii=False)}\n\n" if avoid else "")
        + (f"Recent gegeten: {json.dumps(list(recent), ensure_ascii=False)}\n\n" if recent else "")
        + f"Bestaande recepten:\n{json.dumps(catalog, ensure_ascii=False)}",
        SUGGESTIONS_SCHEMA,
        purpose="Menu-opties",
    )["suggestions"]

    # Alleen suggesties voor gevraagde datums, met geldige verwijzingen en maximaal het gevraagde aantal per dag.
    valid = []
    remaining = dict(needs)
    for s in suggestions:
        if remaining.get(s["date"], 0) <= 0:
            continue
        if s["existing_recipe_id"] is not None and s["existing_recipe_id"] not in known_ids:
            continue
        if s["existing_recipe_id"] is None and s["new_recipe"] is None:
            continue
        remaining[s["date"]] -= 1
        valid.append(s)
    mark_drafts([s["new_recipe"] for s in valid if s["new_recipe"]])
    return valid


def mark_drafts(recipes):
    """Recepten die met vele tegelijk bedacht zijn, zijn een schets: zodra er een in het receptenboek komt, schrijft
    de AI hem volledig uit (zie writer.py). Geeft de recepten terug."""
    for recipe in recipes:
        recipe["draft"] = True
    return recipes


def generate_recipe(request, servings=2, dinner=False):
    """Laat de AI één volledig uitgeschreven recept schrijven op basis van een omschrijving."""
    what = "het avondeten" if dinner else "een recept"
    return _ask(
        GENERATE_SYSTEM, f"Schrijf {what} voor {servings} personen. Wat er gezocht wordt: {request.strip()}", NEW_RECIPE_SCHEMA,
        purpose="Zelf omschreven recept" if dinner else "Recept bedenken",
    )


def write_out_recipe(recipe):
    """Schrijf een kort recept (schets) volledig uit: zelfde gerecht, naam en aantal personen."""
    sketch = {key: recipe.get(key) for key in ("name", "servings", "prep_minutes", "tags", "ingredients", "instructions")}
    full = _ask(
        WRITE_OUT_SYSTEM,
        f"Schrijf dit recept volledig uit, voor {recipe['servings']} personen:\n{json.dumps(sketch, ensure_ascii=False)}",
        NEW_RECIPE_SCHEMA,
        purpose="Recept uitschrijven",
    )
    if not full.get("ingredients") or not str(full.get("instructions") or "").strip():
        raise AIUnavailable(f"{provider_name()} gaf een leeg recept terug. Probeer het opnieuw.", json.dumps(full)[:1000],
                            provider_name())
    return full


def extract_recipe(page_text, url):
    """Haal een recept uit de tekst van een webpagina (als de pagina geen gestructureerd recept heeft)."""
    recipe = _ask(EXTRACT_SYSTEM, f"Pagina: {url}\n\n{page_text}", NEW_RECIPE_SCHEMA, effort="low", purpose="Recept importeren")
    if recipe["name"].strip().upper() == "GEEN RECEPT" or not recipe["ingredients"]:
        from .importer import ImportFailed

        raise ImportFailed("Op deze pagina staat geen recept")
    return recipe


def inspiration(theme, servings=2, count=6):
    """Een collectie van `count` recepten rond een thema."""
    collection = _ask(
        INSPIRATION_SYSTEM,
        f"Stel een collectie van {count} avondgerechten samen voor {servings} personen.\nThema: {theme.strip()}",
        INSPIRATION_SCHEMA,
        purpose="Inspiratie",
    )
    mark_drafts([idea["recipe"] for idea in collection["ideas"]])
    return collection


SWIPE_SYSTEM = f"""Je stelt avondgerechten voor in een swipe-app: de gebruiker ziet per kaart één gerecht met een foto
en één zin, en swipet naar rechts (bewaren) of links (overslaan). Kies gerechten die precies passen bij de
voorkeuren, en varieer binnen de stapel in keuken, hoofdingrediënt en bereidingswijze, zodat er echt iets te
kiezen valt. Stel geen gerecht voor dat op de lijst 'Al gezien' staat, ook niet onder een iets andere naam.
Schrijf per gerecht één korte, smakelijke zin (maximaal 20 woorden) die je doet watertanden, zonder de naam te herhalen.
{RECIPE_RULES}"""

DIETS = {
    "alles": "eet alles",
    "flexitarisch": "flexitarisch: overwegend vegetarisch, soms vlees of vis",
    "vegetarisch": "vegetarisch: geen vlees en geen vis",
    "veganistisch": "veganistisch: geen dierlijke producten",
    "pescotarisch": "pescotarisch: wel vis, geen vlees",
}


def describe_preferences(prefs):
    lines = [f"Dieet: {DIETS.get(prefs.get('diet'), DIETS['alles'])}."]
    if prefs.get("cuisines"):
        lines.append(f"Favoriete keukens: {', '.join(prefs['cuisines'])} (maar af en toe iets anders mag).")
    if prefs.get("max_minutes"):
        lines.append(f"Bereidingstijd: maximaal {prefs['max_minutes']} minuten.")
    if str(prefs.get("avoid") or "").strip():
        lines.append(f"Liever niet / allergieën (nooit gebruiken): {prefs['avoid'].strip()}.")
    return "\n".join(lines)


def swipe_recipes(prefs, count=8, exclude=(), servings=2):
    """Een stapel gerechten om te swipen, passend bij de voorkeuren."""
    seen = ", ".join(list(exclude)[:300]) or "nog niets"
    ideas = _ask(
        SWIPE_SYSTEM,
        f"Stel {count} avondgerechten voor {servings} personen voor.\n{describe_preferences(prefs)}\n\nAl gezien: {seen}",
        SWIPE_SCHEMA,
        purpose="Swipekaarten",
    )["ideas"][:count]
    mark_drafts([idea["recipe"] for idea in ideas])
    return ideas


def photo_prompt(recipe):
    ingredients = ", ".join(i["name"] for i in (recipe.get("ingredients") or [])[:6])
    return (
        f"Appetizing editorial food photograph of the dish \"{recipe['name']}\""
        + (f", made with {ingredients}" if ingredients else "")
        + ". Plated as a home-cooked dinner on a ceramic plate on a wooden table, natural window light, "
        "shallow depth of field, warm tones, shot at a 45-degree angle. Realistic, no text, no people, no hands."
    )


def generate_photo(recipe):
    """Laat Gemini een foto van het gerecht maken; geeft de afbeeldingsbytes terug."""
    model = gemini_models()[1]
    try:
        image = gemini.generate_image(_gemini_key(), model, photo_prompt(recipe))
    except gemini.GeminiError as e:
        raise _from_gemini(e)
    _log_usage("foto", "Gemini", model, "Foto bij recept", cost=image_cost(model))
    return image


def icon_prompt(name, hint=""):
    return (
        f"A single grocery item: \"{name}\" (a Dutch supermarket product name). "
        + (f"Show it like this (description in Dutch): {hint}. " if hint else "")
        + "Simple, friendly flat illustration icon of just this item, centered, filling most of the frame, "
        "on a plain warm cream background (#FBF7F2). Soft colors, subtle shading, rounded shapes, consistent "
        "sticker-like style. No text, no letters, no brand names, no packaging labels, no people."
    )


def generate_icon(name, hint=""):
    """Laat Gemini een vierkant icoon voor een product tekenen, eventueel naar een beschrijving ("een fles");
    geeft de afbeeldingsbytes terug."""
    model = gemini_models()[1]
    try:
        image = gemini.generate_image(_gemini_key(), model, icon_prompt(name, hint), aspect_ratio="1:1")
    except gemini.GeminiError as e:
        raise _from_gemini(e)
    _log_usage("icoon", "Gemini", model, "Icoon (zelf gevraagd)", cost=image_cost(model))
    return image
