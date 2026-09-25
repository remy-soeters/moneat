"""Boodschappenlijst (tegels, suggesties, iconen) en de koppeling met Bring!."""

import json
from http import HTTPStatus

from .. import bring, setting_keys
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


def bring_spec(items):
    """Hoeveelheid voor Bring!, bijv. '500 g' of '2 blikken + 1'."""
    return " + ".join(item["amount"] for item in items if item["amount"])


def register(r, app):
    db, icon_maker = app.db, app.icon_maker

    def with_icons(items, draw=True):
        """Voeg aan elk product het icoon toe (als dat er al is) en laat zo nodig ontbrekende iconen tekenen."""
        names = [i["name"] for i in items]
        icons = db.product_icons(names)
        for item in items:
            item["icon"] = icons.get(item["name"], "")
        if draw:
            icon_maker.request([n for n in names if n not in icons])
        return items

    def bring_auth():
        try:
            return json.loads(db.get_setting(setting_keys.BRING_AUTH) or "null")
        except ValueError:
            return None

    def save_bring_auth(auth):
        db.set_setting(setting_keys.BRING_AUTH, json.dumps(auth) if auth else None)

    def bring_session():
        """Ingelogde Bring!-gegevens, zo nodig met vernieuwde toegang."""
        auth = bring_auth()
        if not auth:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Bring! is nog niet gekoppeld. Doe dat bij Instellingen.")
        if bring.fresh(auth):
            save_bring_auth(auth)
        return auth

    def bring_status():
        auth = bring_auth()
        if not auth:
            return {"connected": False}
        return {"connected": True, "email": auth.get("email"), "list_uuid": auth.get("list_uuid"),
                "list_name": auth.get("list_name")}

    app.bring_status = bring_status  # ook nodig voor de instellingen

    def shopping_response():
        return {
            "bring": bring_status()["connected"],
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

    @r.get("/api/shopping/suggestions")
    def suggestions(req):
        """Voor het toevoegen: wat je waarschijnlijk nodig hebt (op volgorde van kans), aangevuld met gangbare
        boodschappen zolang er weinig geschiedenis is, plus alle bekende producten om in te zoeken."""
        frequent = db.frequent_purchases(24)
        seen = {product_key(f["name"]) for f in frequent}
        staples = [{"name": n, "due": False} for n in STAPLES if product_key(n) not in seen]
        top = [{"name": f["name"], "due": f["due"]} for f in frequent] + staples
        for item in top:
            item["product"] = product_key(item["name"])
        catalog = [{"name": n, "product": product_key(n)} for n in db.product_catalog()]
        return {
            "suggestions": with_icons(top[:30]),
            "catalog": with_icons(catalog, draw=False),  # geen iconen laten tekenen voor alles wat je ooit kookte
            "has_history": bool(frequent),
        }

    # ---------- Bring! (koppelen alleen door een beheerder) ----------

    @r.post("/api/bring/login", admin=True)
    def bring_login(req):
        body = req.json()
        auth = bring.login(str(body.get("email") or "").strip()[:200], str(body.get("password") or "")[:200])
        found = bring.lists(auth)
        default = next((l for l in found if l["uuid"] == auth["list_uuid"]), found[0] if found else None)
        auth["list_uuid"], auth["list_name"] = (default["uuid"], default["name"]) if default else ("", "")
        save_bring_auth(auth)
        db.set_setting(setting_keys.BRING_SYNCED, None)
        return {**bring_status(), "lists": found}

    @r.get("/api/bring/lists", admin=True)
    def bring_lists(req):
        return {**bring_status(), "lists": bring.lists(bring_session())}

    @r.put("/api/bring/list", admin=True)
    def bring_choose_list(req):
        auth = bring_session()
        wanted = str(req.json().get("list_uuid") or "")
        chosen = next((l for l in bring.lists(auth) if l["uuid"] == wanted), None)
        if not chosen:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Deze Bring!-lijst bestaat niet (meer)")
        auth["list_uuid"], auth["list_name"] = chosen["uuid"], chosen["name"]
        save_bring_auth(auth)
        db.set_setting(setting_keys.BRING_SYNCED, None)
        return bring_status()

    @r.delete("/api/bring", admin=True)
    def bring_disconnect(req):
        save_bring_auth(None)
        db.set_setting(setting_keys.BRING_SYNCED, None)
        return bring_status()

    @r.post("/api/bring/sync")
    def bring_sync(req):
        """Zet alles onder 'Kopen' op de Bring!-lijst; wat we eerder stuurden en hier niet meer
        te koop staat, wordt in Bring! afgevinkt. Wat je zelf in Bring! zette, blijft staan."""
        auth = bring_session()
        groups = {}
        for item in db.shopping_list():
            if not item["checked"]:
                groups.setdefault(bring.catalog_name(item["name"]), []).append(item)
        try:
            previous = set(json.loads(db.get_setting(setting_keys.BRING_SYNCED) or "[]"))
        except ValueError:
            previous = set()
        changes = [(name, bring_spec(items), "TO_PURCHASE") for name, items in groups.items()]
        done = sorted(previous - set(groups))
        if done:
            on_list = bring.purchase_names(auth, auth["list_uuid"])
            done = [name for name in done if name in on_list]
            changes += [(name, "", "TO_RECENTLY") for name in done]
        bring.change(auth, auth["list_uuid"], changes)
        db.set_setting(setting_keys.BRING_SYNCED, json.dumps(sorted(groups), ensure_ascii=False))
        return {"sent": len(groups), "checked_off": len(done), "list_name": auth.get("list_name")}
