"""Alle AI in de app: menu-opties, recepten bedenken en uitlezen, inspiratie (Claude of Gemini) en foto's (Gemini)."""

import importlib.util
import json
import os

from . import gemini

MODEL = "claude-opus-5"  # standaard Claude-model
# Keuzes in Instellingen. Haiku kan niet 'nadenken' (adaptive thinking) en kent geen effort-niveau;
# de server-side fallback bij een weigering is er alleen voor Opus 5.
CLAUDE_MODELS = [
    {"id": "claude-opus-5", "name": "Opus 5", "note": "Beste kwaliteit, duurst", "thinking": True, "fallback": True},
    {"id": "claude-sonnet-5", "name": "Sonnet 5", "note": "Bijna even goed, sneller en goedkoper", "thinking": True, "fallback": False},
    {"id": "claude-haiku-4-5", "name": "Haiku 4.5", "note": "Snelst en goedkoopst, eenvoudiger recepten", "thinking": False, "fallback": False},
]


class AIUnavailable(Exception):
    """De AI-functie kan niet draaien (SDK of API-sleutel ontbreekt, of Claude weigerde)."""


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

RECIPE_RULES = """Recepten: Nederlandse namen, ingrediënten in metrische eenheden (g, ml, stuks, el, tl, teen)
met hoeveelheden voor het opgegeven aantal personen, tags als korte kommagescheiden woorden
(bijv. "vegetarisch, pasta, snel"), en een bereiding met één genummerde stap per regel."""

MENU_SYSTEM = f"""Je bent een praktische maaltijdplanner voor een Nederlands huishouden.
Je stelt keuze-opties voor het avondeten samen: per gevraagde datum een paar verschillende gerechten,
waaruit het huishouden er later één kiest. Hergebruik bestaande recepten waar ze passen (zet dan
existing_recipe_id en laat new_recipe null). Stel een nieuw recept voor wanneer dat het menu
gevarieerder maakt of beter bij de wensen past (zet dan new_recipe en laat existing_recipe_id null).
Maak de opties op één dag duidelijk verschillend (bijv. vlees, vis, vegetarisch of snel versus uitgebreid),
herhaal geen gerecht dat al op het menu van die dag staat, en zorg voor afwisseling over de week.
{RECIPE_RULES}
Geef per optie in één zin waarom hij op het menu staat."""

GENERATE_SYSTEM = f"""Je bent een ervaren thuiskok die betrouwbare recepten schrijft voor een Nederlands huishouden.
Schrijf precies het gevraagde gerecht, met ingrediënten die in een gewone Nederlandse supermarkt te krijgen zijn.
{RECIPE_RULES}"""

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

CLAUDE_KEY = "anthropic_api_key"
CLAUDE_MODEL = "claude_model"
GEMINI_KEY = "gemini_api_key"
GEMINI_TEXT_KEY = "gemini_text_api_key"  # optioneel: sleutel uit een project zónder betalen, voor gratis tekst
TEXT_PROVIDER = "text_provider"
GEMINI_TEXT_MODEL = "gemini_text_model"
GEMINI_IMAGE_MODEL = "gemini_image_model"
AUTO_IMAGES = "auto_images"  # "off" = geen foto's/iconen op de achtergrond laten maken


def set_settings(getter):
    global _setting
    _setting = getter


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
    return bool(_setting(GEMINI_KEY) or os.environ.get("GEMINI_API_KEY"))


def auto_images():
    """Mag de app zelf (op de achtergrond) foto's en iconen laten maken? Handmatig kan altijd."""
    return _setting(AUTO_IMAGES) != "off" and gemini_configured()


def _gemini_key():
    key = _setting(GEMINI_KEY) or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise AIUnavailable(
            "Er is nog geen Gemini API-sleutel ingesteld. Voeg er een toe via Instellingen in het menu."
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
            "Het pakket 'anthropic' is niet geïnstalleerd. Kijk bij Instellingen in het menu hoe je dat oplost."
        )
    key = _setting(CLAUDE_KEY)
    try:
        # Een sleutel uit de app gaat voor; anders zoekt de SDK zelf (omgevingsvariabele of `ant auth login`).
        return anthropic, anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError:
        raise AIUnavailable(NO_KEY)


NO_KEY = "Er is nog geen Anthropic API-sleutel ingesteld. Voeg er een toe via Instellingen in het menu."


def check_gemini():
    """Controleer de Gemini-sleutel en modellen, zonder iets te genereren."""
    try:
        text_model, image_model = gemini_models()
        if _setting(GEMINI_TEXT_KEY):
            gemini.check_connection(_setting(GEMINI_TEXT_KEY), [text_model])
            if _setting(GEMINI_KEY) or os.environ.get("GEMINI_API_KEY"):
                gemini.check_connection(_gemini_key(), [image_model])
        else:
            gemini.check_connection(_gemini_key(), [text_model, image_model])
    except gemini.GeminiError as e:
        raise AIUnavailable(str(e))


def check_connection():
    """Controleer of Claude bereikbaar is met de huidige sleutel, zonder tokens te verbruiken."""
    anthropic, client = _client()
    try:
        client.models.retrieve(claude_model()["id"])
    except anthropic.AuthenticationError:
        raise AIUnavailable("Deze API-sleutel wordt niet geaccepteerd. Controleer of je hem volledig hebt geplakt.")
    except anthropic.PermissionDeniedError:
        raise AIUnavailable("Deze API-sleutel heeft geen toegang tot Claude. Controleer je account op console.anthropic.com.")
    except anthropic.APIConnectionError:
        raise AIUnavailable("Kon geen verbinding maken met de Claude API. Controleer je internetverbinding.")
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"Claude API-fout ({e.status_code}): {e.message}")
    except anthropic.AnthropicError:
        raise AIUnavailable(NO_KEY)
    except TypeError as e:
        _raise_if_no_key(e)


def _raise_if_no_key(error):
    """Zonder sleutel geeft de SDK pas bij het versturen een TypeError; maak daar een duidelijke melding van."""
    if "authentication" in str(error).lower():
        raise AIUnavailable(NO_KEY)
    raise error


def _ask(system, user_message, schema, effort="medium"):
    """Stel de gekozen AI een vraag en krijg JSON terug volgens `schema`."""
    if text_provider() == "gemini":
        try:
            return gemini.generate_json(_gemini_text_key(), gemini_models()[0], system, user_message, schema)
        except gemini.GeminiError as e:
            raise AIUnavailable(str(e))
    return _ask_claude(system, user_message, schema, effort)


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
    except anthropic.AuthenticationError:
        raise AIUnavailable("De API-sleutel wordt niet geaccepteerd. Controleer hem bij Instellingen in het menu.")
    except anthropic.RateLimitError:
        raise AIUnavailable("Te veel verzoeken aan Claude; probeer het over een minuut opnieuw.")
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"Claude API-fout ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise AIUnavailable("Kon geen verbinding maken met de Claude API.")
    except anthropic.AnthropicError:
        # Bijvoorbeeld: geen API-sleutel of profiel gevonden.
        raise AIUnavailable(NO_KEY)
    except TypeError as e:
        _raise_if_no_key(e)

    if response.stop_reason == "refusal":
        raise AIUnavailable("Claude kon dit verzoek niet uitvoeren. Formuleer het anders en probeer het opnieuw.")
    if response.stop_reason == "max_tokens":
        raise AIUnavailable("Het antwoord van Claude was te lang en is afgebroken; vraag om minder tegelijk.")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def suggest_menu_options(recipes, needs, current_menu, wishes="", servings=2, avoid=()):
    """Vraag Claude om opties voor het avondeten.

    needs: {datum: aantal opties dat er voor die avond bij moet}
    recipes: bestaande recepten (dicts met id, name, tags, prep_minutes)
    current_menu: opties die al op het menu staan (om dubbelingen te voorkomen)
    avoid: gerechten die net zijn afgewezen ("andere opties"), die niet terug moeten komen
    """
    known_ids = {r["id"] for r in recipes}
    catalog = [
        {"id": r["id"], "name": r["name"], "tags": r["tags"], "prep_minutes": r["prep_minutes"]} for r in recipes
    ]
    wanted = "\n".join(f"- {day}: {count} optie(s)" for day, count in needs.items())
    suggestions = _ask(
        MENU_SYSTEM,
        f"Stel opties voor het avondeten voor. Aantal nieuwe opties per datum:\n{wanted}\n\n"
        f"Aantal personen: {servings}.\n"
        f"Wensen: {wishes.strip() or 'geen bijzondere wensen'}.\n\n"
        f"Staat al op het menu:\n{json.dumps(current_menu, ensure_ascii=False)}\n\n"
        + (f"Net afgewezen, stel deze en vergelijkbare gerechten niet voor: {json.dumps(list(avoid), ensure_ascii=False)}\n\n" if avoid else "")
        + f"Bestaande recepten:\n{json.dumps(catalog, ensure_ascii=False)}",
        SUGGESTIONS_SCHEMA,
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
    return valid


def generate_recipe(request, servings=2):
    """Laat Claude één recept schrijven op basis van een omschrijving."""
    return _ask(GENERATE_SYSTEM, f"Schrijf een recept voor {servings} personen: {request.strip()}", NEW_RECIPE_SCHEMA)


def extract_recipe(page_text, url):
    """Haal een recept uit de tekst van een webpagina (als de pagina geen gestructureerd recept heeft)."""
    recipe = _ask(EXTRACT_SYSTEM, f"Pagina: {url}\n\n{page_text}", NEW_RECIPE_SCHEMA, effort="low")
    if recipe["name"].strip().upper() == "GEEN RECEPT" or not recipe["ingredients"]:
        from .importer import ImportFailed

        raise ImportFailed("Op deze pagina staat geen recept")
    return recipe


def inspiration(theme, servings=2, count=6):
    """Een collectie van `count` recepten rond een thema."""
    return _ask(
        INSPIRATION_SYSTEM,
        f"Stel een collectie van {count} avondgerechten samen voor {servings} personen.\nThema: {theme.strip()}",
        INSPIRATION_SCHEMA,
    )


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
    return _ask(
        SWIPE_SYSTEM,
        f"Stel {count} avondgerechten voor {servings} personen voor.\n{describe_preferences(prefs)}\n\nAl gezien: {seen}",
        SWIPE_SCHEMA,
    )["ideas"][:count]


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
    try:
        return gemini.generate_image(_gemini_key(), gemini_models()[1], photo_prompt(recipe))
    except gemini.GeminiError as e:
        raise AIUnavailable(str(e))


def icon_prompt(name):
    return (
        f"A single grocery item: \"{name}\" (a Dutch supermarket product name). "
        "Simple, friendly flat illustration icon of just this item, centered, filling most of the frame, "
        "on a plain warm cream background (#FBF7F2). Soft colors, subtle shading, rounded shapes, consistent "
        "sticker-like style. No text, no letters, no brand names, no packaging labels, no people."
    )


def generate_icon(name):
    """Laat Gemini een vierkant icoon voor een product tekenen; geeft de afbeeldingsbytes terug."""
    try:
        return gemini.generate_image(_gemini_key(), gemini_models()[1], icon_prompt(name), aspect_ratio="1:1")
    except gemini.GeminiError as e:
        raise AIUnavailable(str(e))
