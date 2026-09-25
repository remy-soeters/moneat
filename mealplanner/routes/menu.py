"""Weekmenu: opties per avond, kiezen, bijzondere avonden, aanvullen met AI en de startpagina."""

from datetime import date, timedelta

from .. import ai
from ..db import week_dates
from .recipes import annotate, servings

MAX_WISHES = 500


def register(r, app):
    db = app.db

    def fill(user, week_day, per_day, wishes, people, only=None, avoid=(), replace=()):
        """Laat de AI komende avonden zonder keuze aanvullen tot `per_day` opties (optioneel alleen `only`).
        Opties in `replace` tellen niet mee en worden pas weggehaald als er nieuwe zijn."""
        menu = db.get_week_menu(week_day)
        replace_ids = {o["id"] for o in replace}
        options = [o for o in menu["options"] if o["id"] not in replace_ids]
        decided = {c["date"] for c in menu["choices"]} | {s["date"] for s in menu["specials"]}
        today = date.today().isoformat()
        needs = {}
        for day in menu["days"]:
            if only is not None and day not in only:
                continue
            count = sum(1 for o in options if o["date"] == day)
            if day >= today and day not in decided and count < per_day:
                needs[day] = per_day - count
        if not needs:
            return 0
        suggestions = ai.suggest_menu_options(
            annotate(db, user["id"], db.list_recipes()),
            needs,
            current_menu=[{"date": o["date"], "gerecht": o["name"]} for o in options],
            wishes=str(wishes or "")[:MAX_WISHES],
            servings=people,
            avoid=avoid,
        )
        for option_id in replace_ids:  # nu pas: lukte de AI niet, dan blijven de oude opties staan
            db.remove_menu_option(option_id)
        added = 0
        for s in suggestions:
            if s["existing_recipe_id"] is not None:
                db.add_menu_option(s["date"], s["existing_recipe_id"], s["reason"], source="claude")
                added += 1
            elif db.add_suggested_option(s["date"], s["new_recipe"], s["reason"]) is not None:
                added += 1
        return added

    def per_day(body):
        return max(1, min(int(body.get("per_day") or 3), 5))

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

    @r.post("/api/menu/special")
    def special(req):
        """Geen recept: uit de vriezer, uit eten, afhalen of restjes."""
        body = req.json()
        db.set_special_dinner(body.get("date"), body.get("kind"), body.get("note"))
        return {"ok": True}

    @r.post("/api/menu/copy-previous")
    def copy_menu(req):
        return {"copied": db.copy_menu_from_previous_week(req.json().get("week"))}

    @r.post("/api/menu/fill")
    def fill_menu(req):
        """Vul komende avonden zonder keuze aan tot `per_day` opties; met `dates` alleen die avonden."""
        body = req.json()
        dates = body.get("dates")
        only = {str(d) for d in dates} if isinstance(dates, list) else None
        added = fill(req.user, body.get("week"), per_day(body), body.get("wishes"), servings(body), only)
        if not added and only is None:
            return {"added": 0, "message": "Elke komende avond heeft al genoeg opties of een keuze."}
        return {"added": added}

    @r.post("/api/menu/refresh")
    def refresh_day(req):
        """'Andere opties': gooi de AI-voorstellen van één avond weg en laat nieuwe bedenken."""
        body = req.json()
        day = str(body.get("date") or "")
        week_dates(day)  # controleert de datum
        old = db.ai_options(day)
        added = fill(req.user, day, per_day(body), body.get("wishes"), servings(body), only={day},
                     avoid=[o["name"] for o in old], replace=old)
        return {"added": added, "removed": len(old)}

    @r.get("/api/home")
    def home(req):
        """Startpagina: vanavond en de komende dagen, plus hoeveel er nog gekocht moet worden."""
        start = req.query.get("today") or date.today().isoformat()
        to_buy = sum(1 for item in db.shopping_list() if not item["checked"])
        days = db.upcoming_dinners(start, 7)
        annotate(db, req.user["id"], [d["recipe"] for d in days if d["recipe"]])
        # Gisteren gegeten en nog niet beoordeeld? Dan vraagt de startpagina hoe het was.
        yesterday = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        unrated = db.unrated_dinner(req.user["id"], yesterday)
        return {"days": days, "to_buy": to_buy, "rate": {"date": yesterday, "recipe": unrated} if unrated else None}
