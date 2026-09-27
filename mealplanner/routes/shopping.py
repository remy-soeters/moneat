"""Boodschappenlijst: tegels, suggesties en iconen."""

from http import HTTPStatus

from .. import ai
from ..db import icon_key
from ..groceries import product_key
from ..importer import parse_ingredient
from ..web import ApiError
from .recipes import servings

# Gangbare boodschappen als startpunt voor de suggesties, zolang er nog weinig geschiedenis is.
STAPLES = [
    "Melk", "Brood", "Eieren", "Kaas", "Boter", "Yoghurt", "Bananen", "Appels", "Tomaten", "Uien",
    "Knoflook", "Aardappelen", "Wortels", "Komkommer", "Paprika", "Sla", "Pasta", "Rijst", "Koffie",
    "Thee", "Olijfolie", "Hagelslag", "Pindakaas", "Wc-papier",
]
MAX_RECIPE_INGREDIENTS = 100
MAX_ICON_HINT = 200


def register(r, app):
    db, images, icon_maker = app.db, app.images, app.icon_maker

    def with_icons(items, draw=True):
        """Voeg aan elk product het icoon toe (als dat er al is) en laat zo nodig ontbrekende iconen tekenen."""
        names = [i["name"] for i in items]
        icons = db.product_icons(names)
        for item in items:
            item["icon"] = icons.get(item["name"], "")
        if draw:
            icon_maker.request([n for n in names if n not in icons])
        return items

    def shopping_response():
        return {
            "items": with_icons(db.shopping_list()),
            "icons": {"pending": icon_maker.pending(), "enabled": icon_maker.enabled(), "failed": icon_maker.failed},
        }

    # ---------- lijst ----------

    @r.get("/api/shopping")
    def get_shopping(req):
        return shopping_response()

    @r.post("/api/shopping/check")
    def check(req):
        body = req.json()
        db.set_shopping_check(str(body.get("key") or ""), bool(body.get("checked")))
        return {"ok": True}

    @r.post("/api/shopping/items")
    def add_item(req):
        parsed = parse_ingredient(str(req.json().get("text") or "")[:200])
        db.add_shopping_item(parsed["name"], parsed["quantity"], parsed["unit"])
        return shopping_response()

    @r.post("/api/shopping/recipe")
    def add_recipe(req):
        body = req.json()
        ingredients = body.get("ingredients")
        if not isinstance(ingredients, list) or not all(isinstance(i, dict) for i in ingredients):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Geen ingrediënten meegestuurd")
        if len(ingredients) > MAX_RECIPE_INGREDIENTS:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Te veel ingrediënten tegelijk")
        recipe_id = body.get("recipe_id")
        people = body.get("servings")
        result = db.add_ingredients_to_list(
            ingredients, int(recipe_id) if recipe_id else None, servings(body) if people else None
        )
        return {**result, **shopping_response()}

    @r.put("/api/shopping/items")
    def update_item(req):
        """Wijzig een product: {key, name, quantity, unit}."""
        body = req.json()
        db.update_shopping_item(str(body.get("key") or ""), body.get("name"), body.get("quantity"), body.get("unit"))
        return shopping_response()

    @r.delete("/api/shopping/items")
    def remove_item(req):
        db.remove_shopping_item(req.param("key"))
        return {"ok": True}

    @r.post("/api/shopping/clear-bought")
    def clear_bought(req):
        return {"removed": db.clear_bought_items()}

    # ---------- iconen: opnieuw laten tekenen, een eigen afbeelding of gewoon de emoji ----------

    def product_name(body):
        name = str(body.get("name") or "").strip()[:80]
        if not icon_key(name):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Voor welk product?")
        return name

    def set_icon(name, image):
        """Geef een product een ander icoon ("" = de emoji, en dan tekent de app er ook geen meer voor)."""
        old = db.product_icons([name]).get(name)
        db.set_product_icon(name, image)
        app.release_image(old)
        return {"icon": image, **shopping_response()}

    @r.post("/api/shopping/icon")
    def draw_icon(req):
        """Laat Gemini een nieuw icoon tekenen, eventueel naar een beschrijving: {name, hint}."""
        body = req.json()
        name = product_name(body)
        image = images.save(ai.generate_icon(name, str(body.get("hint") or "").strip()[:MAX_ICON_HINT]))
        icon_maker.failed = None  # het lukt weer: dan ook op de achtergrond verder tekenen
        return set_icon(name, image)

    @r.put("/api/shopping/icon")
    def choose_icon(req):
        """Een eigen afbeelding (eerst geüpload via /api/images) of "" voor de emoji: {name, image}."""
        body = req.json()
        name = product_name(body)
        image = str(body.get("image") or "")
        if image and not images.path_for(image):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Deze afbeelding bestaat niet (meer); kies hem opnieuw")
        return set_icon(name, image)

    @r.get("/api/shopping/suggestions")
    def suggestions(req):
        """Voor het toevoegen: wat je waarschijnlijk nodig hebt (op volgorde van kans), aangevuld met gangbare
        boodschappen zolang er weinig geschiedenis is, plus alle bekende producten om in te zoeken (met `bought`:
        eerder gekocht, anders een ingrediënt uit je recepten)."""
        frequent = db.frequent_purchases(24)
        seen = {product_key(f["name"]) for f in frequent}
        staples = [{"name": n, "due": False, "bought": False} for n in STAPLES if product_key(n) not in seen]
        top = [{"name": f["name"], "due": f["due"], "bought": True} for f in frequent] + staples
        for item in top:
            item["product"] = product_key(item["name"])
        catalog = [{**p, "product": product_key(p["name"])} for p in db.product_catalog()]
        return {
            "suggestions": with_icons(top[:30]),
            "catalog": with_icons(catalog, draw=False),  # geen iconen laten tekenen voor alles wat je ooit kookte
            "has_history": bool(frequent),
        }
