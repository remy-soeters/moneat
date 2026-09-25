"""Weekmenu: opties per avond, kiezen, bijzondere avonden, aanvullen met AI en de startpagina."""

import re
from datetime import date, timedelta

from .. import ai
from ..db import week_dates
from .recipes import annotate, servings

MAX_WISHES = 500


def dish_key(name):
    """Naam van een gerecht om dubbelingen te herkennen: kleine letters, zonder leestekens."""
    return " ".join(re.sub(r"[^\w\s]", " ", str(name or "").lower()).split())


def register(r, app):
    db = app.db

    def fill(user, week_day, per_day, wishes, people, only=None, avoid=(), replace=()):
        """Laat de AI komende avonden zonder keuze aanvullen tot `per_day` opties (optioneel alleen `only`).
        Opties in `replace` tellen niet mee en worden pas weggehaald als er nieuwe zijn.

        Een gerecht staat maar één keer in de week op het menu, en wat deze week al voorbijkwam zonder
        gekozen te worden (weggeklikt, of een andere avond laten liggen) komt die week niet terug."""
        menu = db.get_week_menu(week_day)
        replace_ids = {o["id"] for o in replace}
        options = [o for o in menu["options"] if o["id"] not in replace_ids]
        chosen = {c["date"]: c["recipe_id"] for c in menu["choices"]}
        decided = set(chosen) | {s["date"] for s in menu["specials"]}
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
        left_over = [o["name"] for o in options
                     if o["date"] in decided and not (o["date"] in chosen and o["recipe_id"] == chosen[o["date"]])]
        passed = list(dict.fromkeys([*avoid, *db.passed_dishes(week_day), *left_over]))
        recipes = annotate(db, user["id"], db.list_recipes())
        suggestions = ai.suggest_menu_options(
            recipes,
            needs,
            current_menu=[{"date": o["date"], "gerecht": o["name"]} for o in options if o["date"] not in decided]
            + [{"date": c["date"], "gerecht": c["recipe_name"], "gekozen": True} for c in menu["choices"]],
            wishes=str(wishes or "")[:MAX_WISHES],
            servings=people,
            avoid=passed,
            recent=db.recent_dinners(menu["days"][0]),
        )
        for option_id in replace_ids:  # nu pas: lukte de AI niet, dan blijven de oude opties staan
            db.remove_menu_option(option_id)
        db.pass_dishes(week_day, [o["name"] for o in replace])

        # Voor de zekerheid ook zelf controleren: geen dubbelingen in de week en niets wat al afgewezen is.
        names = {r["id"]: r["name"] for r in recipes}
        taken_ids = {o["recipe_id"] for o in options if o["recipe_id"] is not None} | set(chosen.values())
        taken = {dish_key(o["name"]) for o in options} | {dish_key(n) for n in passed}
        taken |= {dish_key(c["recipe_name"]) for c in menu["choices"]}
        added = 0
        for s in suggestions:
            recipe_id = s["existing_recipe_id"]
            key = dish_key(names.get(recipe_id, "") if recipe_id is not None else s["new_recipe"]["name"])
            if (recipe_id is not None and recipe_id in taken_ids) or key in taken:
                continue
            if recipe_id is not None:
                db.add_menu_option(s["date"], recipe_id, s["reason"], source="claude")
            elif db.add_suggested_option(s["date"], s["new_recipe"], s["reason"]) is None:
                continue
            taken_ids.add(recipe_id)  # None voor een nieuw recept; dat telt hierboven niet mee
            taken.add(key)
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
