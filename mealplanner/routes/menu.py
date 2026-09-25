"""Weekmenu: opties per avond, kiezen, en aanvullen met AI."""

from datetime import date

from .. import ai
from .recipes import servings

MAX_WISHES = 500


def register(r, app):
    db = app.db

    @r.get("/api/menu")
    def get_menu(req):
        return db.get_week_menu(req.param("week"))

    @r.post("/api/menu/options")
    def add_option(req):
        body = req.json()
        return {"id": db.add_menu_option(body.get("date"), body.get("recipe_id"))}

    @r.delete(r"/api/menu/options/(\d+)")
    def remove_option(req, option_id):
        db.remove_menu_option(int(option_id))
        return {"ok": True}

    @r.post(r"/api/menu/options/(\d+)/choose")
    def choose_option(req, option_id):
        db.choose_option(int(option_id), req.json().get("servings"))
        return {"ok": True}

    @r.post(r"/api/menu/options/(\d+)/save")
    def save_option(req, option_id):
        return {"recipe_id": db.save_option_recipe(int(option_id))}

    @r.delete("/api/menu/choice")
    def clear_choice(req):
        db.clear_dinner_choice(req.param("date"))
        return {"ok": True}

    @r.post("/api/menu/copy-previous")
    def copy_menu(req):
        return {"copied": db.copy_menu_from_previous_week(req.json().get("week"))}

    @r.post("/api/menu/fill")
    def fill_menu(req):
        """Laat de AI elke komende avond zonder keuze aanvullen tot `per_day` opties."""
        body = req.json()
        per_day = max(1, min(int(body.get("per_day") or 3), 5))
        menu = db.get_week_menu(body.get("week"))
        chosen = {c["date"] for c in menu["choices"]}
        today = date.today().isoformat()
        needs = {}
        for day in menu["days"]:
            count = sum(1 for o in menu["options"] if o["date"] == day)
            if day >= today and day not in chosen and count < per_day:
                needs[day] = per_day - count
        if not needs:
            return {"added": 0, "message": "Elke komende avond heeft al genoeg opties of een keuze."}

        suggestions = ai.suggest_menu_options(
            db.list_recipes(),
            needs,
            current_menu=[{"date": o["date"], "gerecht": o["name"]} for o in menu["options"]],
            wishes=str(body.get("wishes") or "")[:MAX_WISHES],
            servings=servings(body),
        )
        added = 0
        for s in suggestions:
            if s["existing_recipe_id"] is not None:
                db.add_menu_option(s["date"], s["existing_recipe_id"], s["reason"], source="claude")
                added += 1
            elif db.add_suggested_option(s["date"], s["new_recipe"], s["reason"]) is not None:
                added += 1
        return {"added": added}
