"""Google Gemini via de Interactions API (REST, alleen standaardbibliotheek).

Tekst: gestructureerde JSON met `response_format`. Beeld: Nano Banana-modellen die een afbeelding teruggeven.
Documentatie: https://ai.google.dev/gemini-api/docs/interactions-overview
"""

import base64
import json
import urllib.error
import urllib.request

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TEXT_MODEL = "gemini-3.8-flash"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"
# Keuzes voor tekst in Instellingen; alle hebben een gratis variant (met limieten), mits de sleutel uit een
# Google-project zonder betaalgegevens komt. Bron: ai.google.dev/gemini-api/docs/pricing
TEXT_MODELS = [
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "note": "Nieuwst en slimst"},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "note": "Sneller en lichter"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "note": "Grondig, maar trager"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "note": "Ouder, betrouwbaar"},
]
# Keuzes voor foto's en iconen in Instellingen; prijzen per foto (1K) volgens ai.google.dev/gemini-api/docs/pricing.
IMAGE_MODELS = [
    {"id": "gemini-3.1-flash-lite-image", "name": "Nano Banana 2 Lite", "price": "± $0,03 per foto", "note": "Goedkoopst, prima voor eten en iconen"},
    {"id": "gemini-2.5-flash-image", "name": "Nano Banana", "price": "± $0,04 per foto", "note": "Eerste versie"},
    {"id": "gemini-3.1-flash-image", "name": "Nano Banana 2", "price": "± $0,07 per foto", "note": "Mooiere details"},
    {"id": "gemini-3-pro-image", "name": "Nano Banana Pro", "price": "± $0,13 per foto", "note": "Beste kwaliteit, duurst"},
]
TIMEOUT = 180


class GeminiError(Exception):
    pass


def _request(api_key, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}/{path}",
        data=data,
        method=method,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise GeminiError(_explain(e.code, _error_message(e)))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GeminiError("Kon geen verbinding maken met Gemini. Controleer je internetverbinding.")


def _error_message(error):
    try:
        return json.load(error).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        return ""


def _explain(status, message):
    if status in (401, 403) and "billing" not in message.lower():
        return "Deze Gemini API-sleutel wordt niet geaccepteerd. Controleer hem bij Instellingen in het menu."
    if status == 429 or "billing" in message.lower() or "free tier" in message.lower():
        return (
            "Gemini weigert dit verzoek vanwege een limiet of omdat betalen nodig is "
            f"(foto's maken kan niet met de gratis variant). Melding van Google: {message or status}"
        )
    if status == 404:
        return f"Dit Gemini-model bestaat niet (meer). Kies een ander model bij Instellingen. ({message})"
    return f"Gemini-fout ({status}): {message or 'onbekende fout'}"


def _check(interaction):
    status = interaction.get("status", "completed")
    if status != "completed":
        raise GeminiError(f"Gemini kon dit verzoek niet afmaken (status: {status}). Probeer het opnieuw.")


def _contents(interaction, kind):
    """Alle content-items van een soort ('text' of 'image') uit de model_output-stappen."""
    for step in interaction.get("steps") or []:
        if step.get("type") == "model_output":
            for item in step.get("content") or []:
                if item.get("type") == kind:
                    yield item


def generate_json(api_key, model, system, user_message, schema):
    """Vraag Gemini om JSON volgens `schema`."""
    interaction = _request(api_key, "POST", "interactions", {
        "model": model,
        "store": False,
        "input": f"{system}\n\n{user_message}",
        "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
    })
    _check(interaction)
    text = interaction.get("output_text") or "".join(item.get("text", "") for item in _contents(interaction, "text"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise GeminiError("Gemini gaf geen bruikbaar antwoord terug. Probeer het opnieuw.")


def generate_image(api_key, model, prompt, aspect_ratio="16:9"):
    """Laat Gemini een afbeelding maken; geeft de bytes terug."""
    interaction = _request(api_key, "POST", "interactions", {
        "model": model,
        "store": False,
        "input": [{"type": "text", "text": prompt}],
        "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": aspect_ratio},
    })
    _check(interaction)
    image = (interaction.get("output_image") or {}).get("data") or next(
        (item.get("data") for item in _contents(interaction, "image") if item.get("data")), None
    )
    if not image:
        raise GeminiError("Gemini heeft geen afbeelding teruggegeven. Probeer het opnieuw.")
    return base64.b64decode(image)


def check_connection(api_key, models):
    """Controleer de sleutel en of de ingestelde modellen beschikbaar zijn (kost niets)."""
    listing = _request(api_key, "GET", "models?pageSize=1000")
    available = {m.get("name", "").removeprefix("models/") for m in listing.get("models", [])}
    missing = [m for m in models if m and available and m not in available]
    if missing:
        raise GeminiError(
            f"De sleutel werkt, maar deze modellen zijn niet beschikbaar: {', '.join(missing)}. "
            "Kies een ander model bij Instellingen."
        )
