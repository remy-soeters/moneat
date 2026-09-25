"""Inspiratie: collecties recepten per thema, met foto's."""

from http import HTTPStatus

from .. import ai
from ..web import ApiError
from .recipes import servings

MAX_THEME = 200


def inspiration_key(theme, people):
    return f"{str(theme or '').strip().lower()}|{int(people or 2)}"


def register(r, app):
    db, images = app.db, app.images

    @r.post("/api/inspiration")
    def inspiration(req):
        body = req.json()
        theme = str(body.get("theme") or "").strip()[:MAX_THEME]
        if not theme:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Kies een thema of typ waar je zin in hebt")
        people = servings(body)
        key = inspiration_key(theme, people)
        if not body.get("refresh"):
            cached = db.get_inspiration(key)
            if cached:
                return cached
        return db.save_inspiration(key, ai.inspiration(theme, people))

    @r.post("/api/inspiration/photo")
    def photo_for_idea(req):
        body = req.json()
        key = inspiration_key(str(body.get("theme") or "")[:MAX_THEME], servings(body))
        collection = db.get_inspiration(key)
        index = int(body.get("index", -1))
        if not collection or not 0 <= index < len(collection["ideas"]):
            raise ApiError(HTTPStatus.NOT_FOUND, "Dit idee bestaat niet (meer); laad de inspiratie opnieuw")
        recipe = collection["ideas"][index]["recipe"]
        old_image = recipe.get("image")
        recipe["image"] = images.save(ai.generate_photo(recipe))
        collection.pop("created_at", None)
        db.save_inspiration(key, collection)
        app.release_image(old_image)
        return {"image": recipe["image"]}
