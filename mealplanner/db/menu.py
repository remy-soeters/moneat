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
                """SELECT c.date, c.recipe_id, c.servings, r.name AS recipe_name, r.image AS recipe_image,
                          EXISTS (SELECT 1 FROM listed_days l WHERE l.date = c.date) AS listed
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
            "choices": [{**dict(r), "listed": bool(r["listed"])} for r in choices],
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

    def pass_dishes(self, any_day, names):
        """Onthoud gerechten die deze week weggeklikt zijn, zodat de AI ze die week niet opnieuw voorstelt."""
        week = week_dates(any_day)[0]
        rows = [(week, str(n).strip()[:150]) for n in names if str(n or "").strip()]
        with self.connect() as conn:
            conn.executemany("INSERT INTO passed_dishes (week, name) VALUES (?, ?) ON CONFLICT DO NOTHING", rows)

    def passed_dishes(self, any_day):
        week = week_dates(any_day)[0]
        with self.connect() as conn:
            rows = conn.execute("SELECT name FROM passed_dishes WHERE week = ? ORDER BY created_at", (week,)).fetchall()
        return [r["name"] for r in rows]

    def recent_dinners(self, before_day, days=14):
        """Namen van wat er in de `days` dagen vóór `before_day` gegeten is."""
        check_date(before_day)
        start = (date.fromisoformat(before_day) - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT r.name FROM dinner_choices c JOIN recipes r ON r.id = c.recipe_id
                   WHERE c.date >= ? AND c.date < ? ORDER BY c.date""",
                (start, before_day),
            ).fetchall()
        return [r["name"] for r in rows]

    def put_dinners_on_list(self, days):
        """Knop "Zet op boodschappenlijst": de ingrediënten van het gekozen avondeten van deze avonden gaan
        op de lijst, en vanaf dan verandert de lijst mee met die avond.

        Een avond die er al op staat, slaan we over: wat je daarvan weghaalde of al kocht en opruimde, komt niet
        terug. Geeft de avonden terug die erbij kwamen.
        """
        added = []
        with self.connect() as conn:
            for day in days:
                check_date(day)
                chosen = conn.execute("SELECT 1 FROM dinner_choices WHERE date = ?", (day,)).fetchone()
                listed = conn.execute("SELECT 1 FROM listed_days WHERE date = ?", (day,)).fetchone()
                if chosen and not listed:
                    conn.execute("INSERT INTO listed_days (date) VALUES (?)", (day,))
                    self._sync_dinner_to_list(day, conn)
                    added.append(day)
        return added

    def reset_dinners(self, days):
        """Knop "Opnieuw beginnen": haal van deze avonden de keuzes, bijzondere avonden en opties weg, en de
        boodschappen daarvan die nog niet gekocht zijn. Bewaarde recepten blijven in het receptenboek."""
        for day in days:
            check_date(day)
        with self.connect() as conn:
            for table in ("dinner_choices", "special_dinners", "menu_options", "listed_days"):
                conn.executemany(f"DELETE FROM {table} WHERE date = ?", [(d,) for d in days])
            conn.executemany("DELETE FROM shopping_items WHERE source_date = ? AND checked = 0", [(d,) for d in days])

    def _sync_dinner_to_list(self, day, conn=None):
        """Houd de boodschappenlijst gelijk met het gekozen avondeten van `day`, als die avond op de lijst staat
        (zie put_dinners_on_list); anders blijft de lijst zoals hij is.

        Nog niet gekochte regels van die avond worden vervangen (andere keuze of ander aantal personen);
        wat al gekocht is blijft staan en komt niet nog eens op de lijst.
        """
        if conn is None:
            with self.connect() as conn:
                return self._sync_dinner_to_list(day, conn)
        if not conn.execute("SELECT 1 FROM listed_days WHERE date = ?", (day,)).fetchone():
            return
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
                "SELECT name, unit FROM shopping_items WHERE source_date = ? AND checked = 1", (day,)
            )
        }
        factor = choice["servings"] / choice["base"]
        ingredients = [
            (ing["name"].strip(), round(ing["quantity"] * factor, 2) if ing["quantity"] is not None else None, ing["unit"].strip())
            for ing in conn.execute(
                "SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position", (choice["recipe_id"],)
            )
        ]
        # Wat je zelf maakt (zoals naan uit je receptenboek) wordt vervangen door de ingrediënten daarvan.
        expanded, _ = self._expand_homemade(conn, ingredients, choice["recipe_id"], choice["servings"])
        for name, quantity, unit, source in expanded:
            if (name.lower(), unit.lower()) in bought:
                continue
            conn.execute(
                """INSERT INTO shopping_items (name, quantity, unit, source_date, source_recipe_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, quantity, unit, day, source or choice["recipe_id"]),
            )


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
