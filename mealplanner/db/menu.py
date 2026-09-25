"""Het weekmenu: opties per avond en de gekozen maaltijd."""

import json
from datetime import date, timedelta

from .base import NotFound
from .cleaning import SPECIAL_DINNERS, check_date, clean_recipe, positive_int, week_dates


class MenuMixin:
    def get_week_menu(self, any_day):
        days = week_dates(any_day)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT o.*, r.name AS recipe_name, r.tags, r.prep_minutes, r.image AS recipe_image
                   FROM menu_options o LEFT JOIN recipes r ON r.id = o.recipe_id
                   WHERE o.date BETWEEN ? AND ?
                   ORDER BY o.date, o.position, o.id""",
                (days[0], days[-1]),
            ).fetchall()
            choices = conn.execute(
                """SELECT c.date, c.recipe_id, c.servings, r.name AS recipe_name, r.image AS recipe_image
                   FROM dinner_choices c JOIN recipes r ON r.id = c.recipe_id
                   WHERE c.date BETWEEN ? AND ?""",
                (days[0], days[-1]),
            ).fetchall()
            specials = conn.execute(
                "SELECT date, kind, note FROM special_dinners WHERE date BETWEEN ? AND ?", (days[0], days[-1])
            ).fetchall()
        return {
            "days": days,
            "options": [_option(r) for r in rows],
            "choices": [dict(r) for r in choices],
            "specials": [_special(r) for r in specials],
        }

    def get_option(self, option_id):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT o.*, r.name AS recipe_name, r.tags, r.prep_minutes, r.image AS recipe_image
                   FROM menu_options o LEFT JOIN recipes r ON r.id = o.recipe_id WHERE o.id = ?""",
                (option_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"Optie {option_id} bestaat niet")
        return _option(row)

    def add_menu_option(self, day, recipe_id, reason="", source="eigen"):
        """Zet een eigen recept op het menu van `day`; staat het er al, dan gebeurt er niets."""
        check_date(day)
        self.get_recipe(recipe_id)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO menu_options (date, recipe_id, source, reason, position)
                   VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM menu_options WHERE date = ?))
                   ON CONFLICT (date, recipe_id) DO NOTHING""",
                (day, recipe_id, source, str(reason or "").strip(), day),
            )
            return conn.execute(
                "SELECT id FROM menu_options WHERE date = ? AND recipe_id = ?", (day, recipe_id)
            ).fetchone()["id"]

    def add_suggested_option(self, day, recipe_data, reason=""):
        """Zet een voorstel van Claude op het menu, zonder het al in het receptenboek te bewaren.

        Geeft None terug als er die avond al een gerecht met dezelfde naam op het menu staat.
        """
        check_date(day)
        recipe = clean_recipe(recipe_data)
        existing = {o["name"].strip().lower() for o in self.get_week_menu(day)["options"] if o["date"] == day}
        if recipe["name"].lower() in existing:
            return None
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO menu_options (date, suggestion, source, reason, position)
                   VALUES (?, ?, 'claude', ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM menu_options WHERE date = ?))""",
                (day, json.dumps(recipe, ensure_ascii=False), str(reason or "").strip(), day),
            )
            return cur.lastrowid

    def remove_menu_option(self, option_id):
        option = self.get_option(option_id)
        with self.connect() as conn:
            conn.execute("DELETE FROM menu_options WHERE id = ?", (option_id,))
            # Een gekozen maaltijd die van het menu verdwijnt, is ook niet meer gekozen.
            if option["recipe_id"] is not None:
                conn.execute(
                    "DELETE FROM dinner_choices WHERE date = ? AND recipe_id = ?", (option["date"], option["recipe_id"])
                )
        self._sync_dinner_to_list(option["date"])

    def save_option_recipe(self, option_id):
        """Bewaar het voorstel achter een optie in het receptenboek. Geeft het recept-id terug."""
        option = self.get_option(option_id)
        if option["recipe_id"] is not None:
            return option["recipe_id"]
        recipe = self.create_recipe(option["suggestion"])
        with self.connect() as conn:
            conn.execute(
                "UPDATE menu_options SET recipe_id = ?, suggestion = NULL WHERE id = ?", (recipe["id"], option_id)
            )
        return recipe["id"]

    def choose_option(self, option_id, servings=None):
        option = self.get_option(option_id)
        self.choose_dinner(option["date"], self.save_option_recipe(option_id), servings)

    def choose_dinner(self, day, recipe_id, servings=None):
        """Kies het avondeten; staat het recept nog niet op het menu, dan komt het erbij."""
        self.add_menu_option(day, recipe_id)
        recipe = self.get_recipe(recipe_id)
        servings = positive_int(servings, recipe["servings"], "Aantal personen")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO dinner_choices (date, recipe_id, servings) VALUES (?, ?, ?)
                   ON CONFLICT (date) DO UPDATE SET recipe_id = excluded.recipe_id, servings = excluded.servings""",
                (day, recipe_id, servings),
            )
            conn.execute("DELETE FROM special_dinners WHERE date = ?", (day,))
        self._sync_dinner_to_list(day)

    def clear_dinner_choice(self, day):
        with self.connect() as conn:
            conn.execute("DELETE FROM dinner_choices WHERE date = ?", (day,))
            conn.execute("DELETE FROM special_dinners WHERE date = ?", (day,))
        self._sync_dinner_to_list(day)

    def set_special_dinner(self, day, kind, note=""):
        """Geen recept die avond (vriezer, uit eten, …): een gekozen recept vervalt, en ook zijn boodschappen."""
        check_date(day)
        if kind not in SPECIAL_DINNERS:
            raise ValueError(f"Onbekende keuze: {kind}")
        with self.connect() as conn:
            conn.execute("DELETE FROM dinner_choices WHERE date = ?", (day,))
            conn.execute(
                """INSERT INTO special_dinners (date, kind, note) VALUES (?, ?, ?)
                   ON CONFLICT (date) DO UPDATE SET kind = excluded.kind, note = excluded.note""",
                (day, kind, str(note or "").strip()[:200]),
            )
        self._sync_dinner_to_list(day)

    def ai_options(self, day):
        """AI-voorstellen van een avond, behalve het gekozen gerecht (die kunnen vervangen worden)."""
        check_date(day)
        with self.connect() as conn:
            chosen = conn.execute("SELECT recipe_id FROM dinner_choices WHERE date = ?", (day,)).fetchone()
            rows = conn.execute(
                """SELECT o.*, r.name AS recipe_name, r.tags, r.prep_minutes, r.image AS recipe_image
                   FROM menu_options o LEFT JOIN recipes r ON r.id = o.recipe_id
                   WHERE o.date = ? AND o.source = 'claude'""",
                (day,),
            ).fetchall()
        return [_option(r) for r in rows if not (chosen and r["recipe_id"] == chosen["recipe_id"])]

    def upcoming_dinners(self, start_day, count=7):
        """Per avond vanaf `start_day`: het gekozen recept (volledig), een bijzondere avond of het aantal opties."""
        first = check_date(start_day)
        days = [(first + timedelta(days=i)).isoformat() for i in range(count)]
        with self.connect() as conn:
            choices = {
                r["date"]: r for r in conn.execute(
                    "SELECT date, recipe_id, servings FROM dinner_choices WHERE date BETWEEN ? AND ?", (days[0], days[-1])
                )
            }
            specials = {
                r["date"]: _special(r) for r in conn.execute(
                    "SELECT date, kind, note FROM special_dinners WHERE date BETWEEN ? AND ?", (days[0], days[-1])
                )
            }
            counts = dict(conn.execute(
                "SELECT date, COUNT(*) FROM menu_options WHERE date BETWEEN ? AND ? GROUP BY date", (days[0], days[-1])
            ).fetchall())
        result = []
        for day in days:
            choice = choices.get(day)
            result.append({
                "date": day,
                "recipe": self.get_recipe(choice["recipe_id"]) if choice else None,
                "servings": choice["servings"] if choice else None,
                "special": specials.get(day),
                "options": counts.get(day, 0),
            })
        return result

    def _sync_dinner_to_list(self, day):
        """Zet de ingrediënten van het gekozen avondeten van `day` op de boodschappenlijst.

        Nog niet gekochte regels van die avond worden vervangen (andere keuze of ander aantal personen);
        wat al gekocht is blijft staan en komt niet nog eens op de lijst.
        """
        with self.connect() as conn:
            conn.execute("DELETE FROM shopping_items WHERE source_date = ? AND checked = 0", (day,))
            choice = conn.execute(
                """SELECT c.recipe_id, c.servings, r.servings AS base FROM dinner_choices c
                   JOIN recipes r ON r.id = c.recipe_id WHERE c.date = ?""",
                (day,),
            ).fetchone()
            if choice is None:
                return
            bought = {
                (r["name"].lower(), r["unit"].lower())
                for r in conn.execute(
                    "SELECT name, unit FROM shopping_items WHERE source_date = ? AND source_recipe_id = ? AND checked = 1",
                    (day, choice["recipe_id"]),
                )
            }
            factor = choice["servings"] / choice["base"]
            for ing in conn.execute("SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position", (choice["recipe_id"],)):
                if (ing["name"].lower(), ing["unit"].lower()) in bought:
                    continue
                quantity = round(ing["quantity"] * factor, 2) if ing["quantity"] is not None else None
                conn.execute(
                    """INSERT INTO shopping_items (name, quantity, unit, source_date, source_recipe_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ing["name"].strip(), quantity, ing["unit"].strip(), day, choice["recipe_id"]),
                )

    def copy_menu_from_previous_week(self, any_day):
        """Zet de opties van vorige week (zonder keuzes) op dezelfde weekdagen van deze week."""
        days = week_dates(any_day)
        previous = week_dates((date.fromisoformat(days[0]) - timedelta(days=7)).isoformat())
        copied = 0
        for option in self.get_week_menu(previous[0])["options"]:
            day = days[previous.index(option["date"])]
            if option["recipe_id"] is not None:
                self.add_menu_option(day, option["recipe_id"], option["reason"], option["source"])
                copied += 1
            elif self.add_suggested_option(day, option["suggestion"], option["reason"]) is not None:
                copied += 1
        return copied


def _option(row):
    """Een menu-optie als dict, met naam/tijd/tags uit het recept of uit het voorstel."""
    option = {
        "id": row["id"],
        "date": row["date"],
        "recipe_id": row["recipe_id"],
        "source": row["source"],
        "reason": row["reason"],
        "saved": row["recipe_id"] is not None,
        "suggestion": None,
    }
    if row["recipe_id"] is not None:
        option.update(
            name=row["recipe_name"], tags=row["tags"], prep_minutes=row["prep_minutes"], image=row["recipe_image"]
        )
    else:
        suggestion = json.loads(row["suggestion"])
        option.update(
            name=suggestion["name"],
            tags=suggestion["tags"],
            prep_minutes=suggestion["prep_minutes"],
            image=suggestion.get("image", ""),
            suggestion=suggestion,
        )
    return option


def _special(row):
    return {"date": row["date"], "kind": row["kind"], "label": SPECIAL_DINNERS.get(row["kind"], row["kind"]), "note": row["note"]}
