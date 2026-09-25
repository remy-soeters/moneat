"""Receptenboek: recepten beheren, importeren, laten bedenken en foto's."""

from http import HTTPStatus

from .. import ai
from ..images import MAX_IMAGE_BYTES
from ..importer import import_recipe
from ..web import ApiError

MAX_PROMPT = 1000


def register(r, app):
    db, images = app.db, app.images

    @r.get("/api/recipes")
    def list_recipes(req):
        return db.list_recipes()

    @r.post("/api/recipes")
    def create_recipe(req):
        return db.create_recipe(req.json())

    @r.get(r"/api/recipes/(\d+)")
    def get_recipe(req, recipe_id):
        return db.get_recipe(int(recipe_id))

    @r.put(r"/api/recipes/(\d+)")
    def update_recipe(req, recipe_id):
        old_image = db.get_recipe(int(recipe_id))["image"]
        recipe = db.update_recipe(int(recipe_id), req.json())
        if old_image != recipe["image"]:
            app.release_image(old_image)
        return recipe

    @r.delete(r"/api/recipes/(\d+)")
    def delete_recipe(req, recipe_id):
        image = db.get_recipe(int(recipe_id))["image"]
        db.delete_recipe(int(recipe_id))
        app.release_image(image)
        return {"ok": True}

    @r.post("/api/recipes/import")
    def import_from_url(req):
        url = str(req.json().get("url") or "").strip()
        if not url:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Plak eerst een link naar een recept")
        if len(url) > 2000:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Deze link is te lang")
        if "://" not in url:
            url = "https://" + url
        return import_recipe(url, images, ai_extract=ai.extract_recipe)

    @r.post("/api/recipes/generate")
    def generate(req):
        body = req.json()
        request = str(body.get("prompt") or "").strip()[:MAX_PROMPT]
        if not request:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Beschrijf eerst wat je wilt maken")
        return ai.generate_recipe(request, servings(body))

    @r.post("/api/images")
    def upload_image(req):
        return {"image": images.save(req.body(limit=MAX_IMAGE_BYTES))}

    # ---------- foto's maken ----------

    @r.post("/api/photos/draft")
    def photo_for_draft(req):
        recipe = req.json().get("recipe") or {}
        if not isinstance(recipe, dict) or not str(recipe.get("name") or "").strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, "Geef het recept eerst een naam")
        return {"image": images.save(ai.generate_photo(recipe))}

    @r.post(r"/api/recipes/(\d+)/photo")
    def photo_for_recipe(req, recipe_id):
        recipe = db.get_recipe(int(recipe_id))
        old_image = recipe["image"]
        recipe["image"] = images.save(ai.generate_photo(recipe))
        recipe = db.update_recipe(recipe["id"], recipe)
        app.release_image(old_image)
        return recipe


def servings(body, default=2):
    """Aantal personen uit een verzoek, tussen 1 en 20."""
    try:
        value = int(body.get("servings") or default)
    except (TypeError, ValueError):
        raise ValueError("Aantal personen moet een getal zijn") from None
    return max(1, min(value, 20))
