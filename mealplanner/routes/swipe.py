"""Recepten swipen: voorkeuren, kaarten en de voorraad die op de achtergrond klaargezet wordt."""

import json

from .. import ai, setting_keys
from .recipes import servings

MAX_MINUTES = (None, 20, 30, 45, 60)


def clean_preferences(data):
    """Controleer de voedselvoorkeuren uit het swipe-formulier."""
    diet = data.get("diet") or "alles"
    if diet not in ai.DIETS:
        raise ValueError(f"Onbekend dieet: {diet}")
    cuisines = data.get("cuisines") or []
    if not isinstance(cuisines, list) or len(cuisines) > 12:
        raise ValueError("Kies maximaal 12 keukens")
    cuisines = [str(c).strip()[:30] for c in cuisines if str(c).strip()]
    max_minutes = data.get("max_minutes") or None
    if max_minutes is not None:
        max_minutes = int(max_minutes)
    if max_minutes not in MAX_MINUTES:
        raise ValueError("Kies 20, 30, 45 of 60 minuten, of geen maximum")
    return {
        "diet": diet,
        "cuisines": cuisines,
        "max_minutes": max_minutes,
        "avoid": str(data.get("avoid") or "").strip()[:200],
    }


def register(r, app):
    db, images, preloader = app.db, app.images, app.preloader

    @r.get("/api/preferences")
    def get_preferences(req):
        return app.load_preferences()

    @r.put("/api/preferences")
    def save_preferences(req):
        prefs = clean_preferences(req.json())
        db.set_setting(setting_keys.PREFERENCES, json.dumps(prefs, ensure_ascii=False))
        preloader.kick()
        return prefs

    @r.get("/api/swipe")
    def get_swipe(req):
        return {
            "cards": db.pending_swipe_cards(),
            "stats": db.swipe_stats(),
            "preferences": app.load_preferences(),
            "preload": preloader.status(),
        }

    @r.post("/api/swipe/preload")
    def preload(req):
        body = req.json()
        preloader.kick(servings(body) if body.get("servings") else None, retry=bool(body.get("retry")))
        return preloader.status()

    @r.post("/api/swipe/more")
    def more_cards(req):
        body = req.json()
        count = max(1, min(int(body.get("count") or 8), 12))
        ideas = ai.swipe_recipes(app.load_preferences(), count, exclude=db.known_dish_names(), servings=servings(body))
        return {"added": db.add_swipe_cards(ideas), "cards": db.pending_swipe_cards()}

    @r.post(r"/api/swipe/cards/(\d+)/photo")
    def card_photo(req, card_id):
        card = db.get_swipe_card(int(card_id))
        with ai.usage("Foto voor swipekaart"):
            image = images.save(ai.generate_photo(card["recipe"]))
        db.set_swipe_card_image(card["id"], image)
        app.release_image(card["image"])
        return {"image": image}

    @r.post(r"/api/swipe/cards/(\d+)")
    def swipe(req, card_id):
        recipe = db.swipe(int(card_id), bool(req.json().get("liked")))
        preloader.kick()  # voorraad weer aanvullen
        if recipe and recipe["draft"]:
            app.writer.kick()  # het bewaarde gerecht volledig laten uitschrijven
        return {"recipe": recipe, "stats": db.swipe_stats()}

    @r.delete("/api/swipe/pending")
    def clear_cards(req):
        for image in db.clear_pending_swipe_cards():
            app.release_image(image)
        preloader.kick()
        return {"ok": True}

    @r.post("/api/swipe/undo")
    def undo(req):
        return {"card": db.undo_swipe(), "stats": db.swipe_stats()}
