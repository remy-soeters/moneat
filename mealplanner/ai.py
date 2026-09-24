"""Alle AI in de app: menu-opties, recepten bedenken en uitlezen, inspiratie (Claude of Gemini) en foto's (Gemini)."""

import importlib.util
import json
import os

from . import gemini

MODEL = "claude-opus-5"


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
GEMINI_KEY = "gemini_api_key"
TEXT_PROVIDER = "text_provider"
GEMINI_TEXT_MODEL = "gemini_text_model"
GEMINI_IMAGE_MODEL = "gemini_image_model"


def set_settings(getter):
    global _setting
    _setting = getter


def text_provider():
    return _setting(TEXT_PROVIDER, "claude")


def provider_name():
    return "Gemini" if text_provider() == "gemini" else "Claude"


def gemini_models():
    return (
        _setting(GEMINI_TEXT_MODEL) or gemini.DEFAULT_TEXT_MODEL,
        _setting(GEMINI_IMAGE_MODEL) or gemini.DEFAULT_IMAGE_MODEL,
    )


def _gemini_key():
    key = _setting(GEMINI_KEY) or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise AIUnavailable(
            "Er is nog geen Gemini API-sleutel ingesteld. Voeg er een toe via Instellingen (tandwiel rechtsboven)."
        )
    return key


def sdk_installed():
    return importlib.util.find_spec("anthropic") is not None


def env_key_present():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _client():
    try:
        import anthropic
    except ImportError:
        raise AIUnavailable(
            "Het pakket 'anthropic' is niet geïnstalleerd. Kijk bij Instellingen (tandwiel rechtsboven) hoe je dat oplost."
        )
    key = _setting(CLAUDE_KEY)
    try:
        # Een sleutel uit de app gaat voor; anders zoekt de SDK zelf (omgevingsvariabele of `ant auth login`).
        return anthropic, anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError:
        raise AIUnavailable(NO_KEY)


NO_KEY = "Er is nog geen Anthropic API-sleutel ingesteld. Voeg er een toe via Instellingen (tandwiel rechtsboven)."


def check_gemini():
    """Controleer de Gemini-sleutel en modellen, zonder iets te genereren."""
    try:
        gemini.check_connection(_gemini_key(), gemini_models())
    except gemini.GeminiError as e:
        raise AIUnavailable(str(e))


def check_connection():
    """Controleer of Claude bereikbaar is met de huidige sleutel, zonder tokens te verbruiken."""
    anthropic, client = _client()
    try:
        client.models.retrieve(MODEL)
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
            return gemini.generate_json(_gemini_key(), gemini_models()[0], system, user_message, schema)
        except gemini.GeminiError as e:
            raise AIUnavailable(str(e))
    return _ask_claude(system, user_message, schema, effort)


def _ask_claude(system, user_message, schema, effort):
    """Stel Claude een vraag en krijg JSON terug volgens `schema`."""
    anthropic, client = _client()
    try:
        # Streaming, omdat een volle week of een collectie recepten een lang antwoord kan opleveren.
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise AIUnavailable("De API-sleutel wordt niet geaccepteerd. Controleer hem bij Instellingen (tandwiel rechtsboven).")
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


def suggest_menu_options(recipes, needs, current_menu, wishes="", servings=2):
    """Vraag Claude om opties voor het avondeten.

    needs: {datum: aantal opties dat er voor die avond bij moet}
    recipes: bestaande recepten (dicts met id, name, tags, prep_minutes)
    current_menu: opties die al op het menu staan (om dubbelingen te voorkomen)
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
        f"Bestaande recepten:\n{json.dumps(catalog, ensure_ascii=False)}",
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
