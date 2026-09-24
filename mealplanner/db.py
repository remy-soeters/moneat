"""SQLite-opslag voor recepten, weekmenu (avondeten) en boodschappenlijst."""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    servings      INTEGER NOT NULL DEFAULT 2 CHECK (servings > 0),
    prep_minutes  INTEGER,
    instructions  TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '',
    image         TEXT NOT NULL DEFAULT '',
    source_url    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ingredients (
    id         INTEGER PRIMARY KEY,
    recipe_id  INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL,
    quantity   REAL,
    unit       TEXT NOT NULL DEFAULT ''
);

-- Opties op het weekmenu: per avond een paar gerechten waaruit je kiest. Een optie is een eigen
-- recept (recipe_id) of een voorstel van Claude dat nog niet in het receptenboek staat (suggestion).
CREATE TABLE IF NOT EXISTS menu_options (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    recipe_id   INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
    suggestion  TEXT,
    source      TEXT NOT NULL DEFAULT 'eigen' CHECK (source IN ('eigen', 'claude')),
    reason      TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    CHECK ((recipe_id IS NULL) <> (suggestion IS NULL)),
    UNIQUE (date, recipe_id)
);

-- De gekozen maaltijd per avond.
CREATE TABLE IF NOT EXISTS dinner_choices (
    date       TEXT PRIMARY KEY,
    recipe_id  INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    servings   INTEGER NOT NULL CHECK (servings > 0)
);

-- Bewaarde inspiratie van Claude, zodat een thema niet elke keer opnieuw gegenereerd hoeft te worden.
CREATE TABLE IF NOT EXISTS inspiration (
    key         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    payload     TEXT NOT NULL
);

-- Kaarten om te swipen: voorstellen die je bewaart (naar rechts) of overslaat (naar links).
CREATE TABLE IF NOT EXISTS swipe_cards (
    id           INTEGER PRIMARY KEY,
    recipe       TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    image        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'liked', 'skipped')),
    recipe_id    INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    swiped_at    TEXT
);

-- Instellingen van de app, zoals de Anthropic API-sleutel.
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Eén doorlopende boodschappenlijst. Regels komen van een gekozen avondeten (source_date + recipe)
-- of zijn zelf toegevoegd (geen bron). Gelijke producten worden in de weergave samengevoegd.
CREATE TABLE IF NOT EXISTS shopping_items (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    quantity          REAL,
    unit              TEXT NOT NULL DEFAULT '',
    checked           INTEGER NOT NULL DEFAULT 0,
    source_date       TEXT,
    source_recipe_id  INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Iconen per product (door Gemini getekend), één keer gemaakt en daarna hergebruikt.
CREATE TABLE IF NOT EXISTS product_icons (
    key    TEXT PRIMARY KEY,
    image  TEXT NOT NULL
);

-- Hoe vaak iets gekocht is, voor de suggesties "vaak gekocht".
CREATE TABLE IF NOT EXISTS purchase_counts (
    key      TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    last_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

"""


class NotFound(Exception):
    pass


class Database:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        # Een geheugendatabase (tests) deelt één verbinding; laat threads die om de beurt gebruiken.
        self._memory_lock = threading.RLock()
        with self.connect() as conn:
            had_list = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopping_items'"
            ).fetchone() is not None
            _rename_old_menu_options(conn)
            _add_missing_recipe_columns(conn)
            conn.executescript(SCHEMA)
            _migrate_old_menu_options(conn)
            _migrate_plan_entries(conn)
            if _migrate_week_shopping(conn) or not had_list:
                self._pending_list_migration = True
        self._finish_migrations()

    _pending_list_migration = False

    def _finish_migrations(self):
        """Na het omzetten naar één lijst: zet gekozen avondeten vanaf vandaag er één keer op."""
        if self._pending_list_migration:
            self._pending_list_migration = False
            with self.connect() as conn:
                days = [r["date"] for r in conn.execute("SELECT date FROM dinner_choices WHERE date >= date('now')")]
            for day in days:
                self._sync_dinner_to_list(day)

    @contextmanager
    def connect(self):
        """Verbinding binnen één transactie; commit bij succes, rollback bij een fout."""
        if self._memory_conn is not None:
            with self._memory_lock:
                conn = self._memory_conn
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:
                    yield conn
            return
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ---------- recepten ----------

    def list_recipes(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM recipes ORDER BY name COLLATE NOCASE").fetchall()
            return [self._recipe_with_ingredients(conn, row) for row in rows]

    def get_recipe(self, recipe_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            if row is None:
                raise NotFound(f"Recept {recipe_id} bestaat niet")
            return self._recipe_with_ingredients(conn, row)

    def create_recipe(self, data):
        recipe = _clean_recipe(data)
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO recipes (name, servings, prep_minutes, instructions, tags, image, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (recipe["name"], recipe["servings"], recipe["prep_minutes"], recipe["instructions"], recipe["tags"],
                 recipe["image"], recipe["source_url"]),
            )
            self._replace_ingredients(conn, cur.lastrowid, recipe["ingredients"])
            recipe_id = cur.lastrowid
        return self.get_recipe(recipe_id)

    def update_recipe(self, recipe_id, data):
        recipe = _clean_recipe(data)
        with self.connect() as conn:
            cur = conn.execute(
                """UPDATE recipes SET name = ?, servings = ?, prep_minutes = ?, instructions = ?, tags = ?,
                                      image = ?, source_url = ?
                   WHERE id = ?""",
                (recipe["name"], recipe["servings"], recipe["prep_minutes"], recipe["instructions"], recipe["tags"],
                 recipe["image"], recipe["source_url"], recipe_id),
            )
            if cur.rowcount == 0:
                raise NotFound(f"Recept {recipe_id} bestaat niet")
            self._replace_ingredients(conn, recipe_id, recipe["ingredients"])
            days = [r["date"] for r in conn.execute("SELECT date FROM dinner_choices WHERE recipe_id = ?", (recipe_id,))]
        for day in days:  # gewijzigde ingrediënten ook op de boodschappenlijst doorvoeren
            self._sync_dinner_to_list(day)
        return self.get_recipe(recipe_id)

    def delete_recipe(self, recipe_id):
        with self.connect() as conn:
            conn.execute("DELETE FROM shopping_items WHERE source_recipe_id = ? AND checked = 0", (recipe_id,))
            cur = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
            if cur.rowcount == 0:
                raise NotFound(f"Recept {recipe_id} bestaat niet")

    def _replace_ingredients(self, conn, recipe_id, ingredients):
        conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
        conn.executemany(
            "INSERT INTO ingredients (recipe_id, position, name, quantity, unit) VALUES (?, ?, ?, ?, ?)",
            [(recipe_id, i, ing["name"], ing["quantity"], ing["unit"]) for i, ing in enumerate(ingredients)],
        )

    def _recipe_with_ingredients(self, conn, row):
        recipe = dict(row)
        recipe["ingredients"] = [
            {"name": r["name"], "quantity": r["quantity"], "unit": r["unit"]}
            for r in conn.execute(
                "SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position", (row["id"],)
            )
        ]
        return recipe

    # ---------- weekmenu ----------

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
                """SELECT c.date, c.recipe_id, c.servings, r.name AS recipe_name
                   FROM dinner_choices c JOIN recipes r ON r.id = c.recipe_id
                   WHERE c.date BETWEEN ? AND ?""",
                (days[0], days[-1]),
            ).fetchall()
        return {"days": days, "options": [_option(r) for r in rows], "choices": [dict(r) for r in choices]}

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
        _check_date(day)
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
        _check_date(day)
        recipe = _clean_recipe(recipe_data)
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
        servings = _positive_int(servings, recipe["servings"], "Aantal personen")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO dinner_choices (date, recipe_id, servings) VALUES (?, ?, ?)
                   ON CONFLICT (date) DO UPDATE SET recipe_id = excluded.recipe_id, servings = excluded.servings""",
                (day, recipe_id, servings),
            )
        self._sync_dinner_to_list(day)

    def clear_dinner_choice(self, day):
        with self.connect() as conn:
            conn.execute("DELETE FROM dinner_choices WHERE date = ?", (day,))
        self._sync_dinner_to_list(day)

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

    # ---------- afbeeldingen en inspiratie ----------

    def image_in_use(self, image):
        """Wordt deze afbeelding nog gebruikt door een recept, een voorstel op het menu of inspiratie?"""
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipes WHERE image = ?", (image,)).fetchone():
                return True
            if conn.execute("SELECT 1 FROM product_icons WHERE image = ?", (image,)).fetchone():
                return True
            pattern = f'%"image": "{image}"%'
            return (
                conn.execute("SELECT 1 FROM menu_options WHERE suggestion LIKE ?", (pattern,)).fetchone()
                or conn.execute("SELECT 1 FROM inspiration WHERE payload LIKE ?", (pattern,)).fetchone()
                or conn.execute("SELECT 1 FROM swipe_cards WHERE image = ?", (image,)).fetchone()
            ) is not None

    def get_inspiration(self, key):
        with self.connect() as conn:
            row = conn.execute("SELECT created_at, payload FROM inspiration WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return {**json.loads(row["payload"]), "created_at": row["created_at"]}

    def save_inspiration(self, key, payload):
        created = date.today().isoformat()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO inspiration (key, created_at, payload) VALUES (?, ?, ?)
                   ON CONFLICT (key) DO UPDATE SET created_at = excluded.created_at, payload = excluded.payload""",
                (key, created, json.dumps(payload, ensure_ascii=False)),
            )
        return {**payload, "created_at": created}

    # ---------- swipen ----------

    def add_swipe_cards(self, ideas):
        """Voeg nieuwe kaarten toe (dicts met recipe en description); dubbele namen worden overgeslagen."""
        seen = {name.lower() for name in self.known_dish_names()}
        added = 0
        with self.connect() as conn:
            for idea in ideas:
                recipe = _clean_recipe(idea["recipe"])
                if recipe["name"].lower() in seen:
                    continue
                seen.add(recipe["name"].lower())
                conn.execute(
                    "INSERT INTO swipe_cards (recipe, description) VALUES (?, ?)",
                    (json.dumps(recipe, ensure_ascii=False), str(idea.get("description") or "").strip()),
                )
                added += 1
        return added

    def known_dish_names(self, limit=400):
        """Namen die niet opnieuw voorgesteld moeten worden: eerdere kaarten en recepten in het boek."""
        with self.connect() as conn:
            cards = conn.execute(
                "SELECT json_extract(recipe, '$.name') AS name FROM swipe_cards ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            recipes = conn.execute("SELECT name FROM recipes").fetchall()
        return [r["name"] for r in cards + recipes if r["name"]]

    def pending_swipe_cards(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM swipe_cards WHERE status = 'pending' ORDER BY id").fetchall()
        return [_card(r) for r in rows]

    def get_swipe_card(self, card_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM swipe_cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            raise NotFound(f"Kaart {card_id} bestaat niet")
        return _card(row)

    def set_swipe_card_image(self, card_id, image):
        with self.connect() as conn:
            conn.execute("UPDATE swipe_cards SET image = ? WHERE id = ?", (image, card_id))

    def swipe(self, card_id, liked):
        """Verwerk een swipe. Naar rechts: het recept (met foto) komt in het receptenboek."""
        card = self.get_swipe_card(card_id)
        if card["status"] != "pending":
            raise ValueError("Deze kaart is al geswipet")
        recipe = None
        if liked:
            recipe = self.create_recipe({**card["recipe"], "image": card["image"]})
        with self.connect() as conn:
            conn.execute(
                "UPDATE swipe_cards SET status = ?, recipe_id = ?, swiped_at = datetime('now') WHERE id = ?",
                ("liked" if liked else "skipped", recipe["id"] if recipe else None, card_id),
            )
        return recipe

    def undo_swipe(self):
        """Zet de laatste swipe terug; een bewaard recept gaat weer uit het receptenboek."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM swipe_cards WHERE status != 'pending' ORDER BY swiped_at DESC, id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        if row["recipe_id"]:
            self.delete_recipe(row["recipe_id"])
        with self.connect() as conn:
            conn.execute(
                "UPDATE swipe_cards SET status = 'pending', recipe_id = NULL, swiped_at = NULL WHERE id = ?", (row["id"],)
            )
        return self.get_swipe_card(row["id"])

    def clear_pending_swipe_cards(self):
        """Gooi kaarten weg die nog niet geswipet zijn (bijv. na nieuwe voorkeuren); geeft hun foto's terug."""
        with self.connect() as conn:
            images = [r["image"] for r in conn.execute("SELECT image FROM swipe_cards WHERE status = 'pending'")]
            conn.execute("DELETE FROM swipe_cards WHERE status = 'pending'")
        return [image for image in images if image]

    def swipe_stats(self):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT SUM(status = 'liked') AS liked, SUM(status = 'skipped') AS skipped,
                          SUM(status = 'liked' AND date(swiped_at) = date('now')) AS liked_today
                   FROM swipe_cards"""
            ).fetchone()
        return {key: row[key] or 0 for key in ("liked", "skipped", "liked_today")}

    # ---------- instellingen ----------

    def get_setting(self, key, default=None):
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        with self.connect() as conn:
            if value is None:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    """INSERT INTO settings (key, value) VALUES (?, ?)
                       ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
                    (key, value),
                )

    # ---------- boodschappenlijst ----------

    def shopping_list(self):
        """De hele lijst, met gelijke producten (naam + eenheid) samengevoegd tot één regel."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.*, r.name AS recipe FROM shopping_items s
                   LEFT JOIN recipes r ON r.id = s.source_recipe_id
                   ORDER BY s.id"""
            ).fetchall()
        groups = {}
        for row in rows:
            key = f"{'bought' if row['checked'] else 'buy'}:{row['name'].strip().lower()}|{row['unit'].strip().lower()}"
            item = groups.setdefault(key, {
                "key": key, "name": row["name"].strip(), "unit": row["unit"].strip(), "quantity": None,
                "recipes": [], "checked": bool(row["checked"]), "manual": False,
            })
            if row["quantity"] is not None:
                item["quantity"] = round((item["quantity"] or 0) + row["quantity"], 2)
            if row["recipe"] and row["recipe"] not in item["recipes"]:
                item["recipes"].append(row["recipe"])
            if row["source_date"] is None:
                item["manual"] = True
        return list(groups.values())

    def _group_rows(self, conn, key):
        state, _, rest = key.partition(":")
        name, _, unit = rest.partition("|")
        if state not in ("buy", "bought") or not name:
            raise NotFound("Dit product staat niet (meer) op de lijst")
        rows = conn.execute(
            "SELECT id, name FROM shopping_items WHERE lower(trim(name)) = ? AND lower(trim(unit)) = ? AND checked = ?",
            (name, unit, int(state == "bought")),
        ).fetchall()
        if not rows:
            raise NotFound("Dit product staat niet (meer) op de lijst")
        return rows

    def add_shopping_item(self, name, quantity=None, unit=""):
        name = str(name or "").strip()
        if not name:
            raise ValueError("Wat wil je op de lijst zetten?")
        with self.connect() as conn:
            # Al zelf toegevoegd en nog niet gekocht? Dan de hoeveelheid ophogen in plaats van dubbel toevoegen.
            existing = conn.execute(
                """SELECT id FROM shopping_items WHERE source_date IS NULL AND checked = 0
                   AND lower(name) = lower(?) AND unit = ?""",
                (name, unit),
            ).fetchone()
            if existing:
                if quantity is not None:
                    conn.execute(
                        "UPDATE shopping_items SET quantity = COALESCE(quantity, 0) + ? WHERE id = ?", (quantity, existing["id"])
                    )
                return existing["id"]
            return conn.execute(
                "INSERT INTO shopping_items (name, quantity, unit) VALUES (?, ?, ?)", (name[:80], quantity, unit)
            ).lastrowid

    def remove_shopping_item(self, key):
        """Haal een (samengevoegd) product van de lijst."""
        with self.connect() as conn:
            ids = [r["id"] for r in self._group_rows(conn, key)]
            conn.execute(f"DELETE FROM shopping_items WHERE id IN ({','.join('?' * len(ids))})", ids)

    def clear_bought_items(self):
        """Haal alles wat al gekocht is van de lijst."""
        with self.connect() as conn:
            return conn.execute("DELETE FROM shopping_items WHERE checked = 1").rowcount

    def set_shopping_check(self, key, checked):
        """Markeer een (samengevoegd) product als gekocht of zet het terug; telt mee voor "vaak gekocht"."""
        with self.connect() as conn:
            rows = self._group_rows(conn, key)
            if key.startswith("bought:") == bool(checked):
                return  # staat al zo
            ids = [r["id"] for r in rows]
            conn.execute(
                f"UPDATE shopping_items SET checked = ? WHERE id IN ({','.join('?' * len(ids))})", [int(bool(checked)), *ids]
            )
            self._count_purchase(conn, rows[0]["name"], 1 if checked else -1)

    def frequent_purchases(self, limit=24):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name, count FROM purchase_counts WHERE count > 0 ORDER BY count DESC, last_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"name": r["name"], "count": r["count"]} for r in rows]

    def product_icons(self, names):
        """{naam: afbeelding} voor de producten die al een icoon hebben."""
        keys = {icon_key(n): n for n in names if icon_key(n)}
        if not keys:
            return {}
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT key, image FROM product_icons WHERE key IN ({','.join('?' * len(keys))})", list(keys)
            ).fetchall()
        return {keys[r["key"]]: r["image"] for r in rows}

    def set_product_icon(self, name, image):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO product_icons (key, image) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET image = excluded.image",
                (icon_key(name), image),
            )

    def _count_purchase(self, conn, name, delta):
        key = name.strip().lower()
        if not key:
            return
        if delta > 0:
            conn.execute(
                """INSERT INTO purchase_counts (key, name, count) VALUES (?, ?, 1)
                   ON CONFLICT (key) DO UPDATE SET count = count + 1, name = excluded.name, last_at = datetime('now')""",
                (key, name.strip()),
            )
        else:
            conn.execute("UPDATE purchase_counts SET count = MAX(count - 1, 0) WHERE key = ?", (key,))


# ---------- hulpfuncties ----------


def week_dates(any_day):
    """De zeven datums (ma t/m zo) van de week waarin `any_day` valt."""
    d = _check_date(any_day)
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


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


def _add_missing_recipe_columns(conn):
    """Oudere databases hebben nog geen kolommen voor foto en bron."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(recipes)")]
    if not columns:
        return
    for column in ("image", "source_url"):
        if column not in columns:
            conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def _clean_image(value):
    value = str(value or "").strip()
    if value and not re.fullmatch(r"/images/[0-9a-f]{32}\.(jpg|png|gif|webp)", value):
        raise ValueError("Ongeldige afbeelding")
    return value


def _clean_url(value):
    value = str(value or "").strip()
    if value and not re.match(r"https?://", value):
        raise ValueError("De bron moet een http- of https-link zijn")
    return value[:2000]


def icon_key(name):
    """Eén icoon per product, ongeacht hoofdletters of spaties: 'Rode ui ' en 'rode ui' delen er een."""
    return " ".join(str(name or "").lower().split())[:60]


def _card(row):
    return {
        "id": row["id"],
        "recipe": json.loads(row["recipe"]),
        "description": row["description"],
        "image": row["image"],
        "status": row["status"],
        "recipe_id": row["recipe_id"],
    }


def _migrate_week_shopping(conn):
    """Eerdere versie had een lijst per week. Zet zelf toegevoegde producten over; geeft True als er omgezet is."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(shopping_items)")]
    if "week_start" not in columns:
        return False
    conn.execute("ALTER TABLE shopping_items RENAME TO shopping_items_week")
    conn.executescript(SCHEMA)
    conn.execute(
        """INSERT INTO shopping_items (name, quantity, unit, checked, created_at)
           SELECT name, quantity, unit, checked, created_at FROM shopping_items_week"""
    )
    conn.execute("DROP TABLE shopping_items_week")
    return True


def _rename_old_menu_options(conn):
    """De eerste versie van menu_options had geen id-kolom; zet die tabel opzij om over te nemen."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(menu_options)")]
    if columns and "id" not in columns:
        conn.execute("ALTER TABLE menu_options RENAME TO menu_options_v1")


def _migrate_old_menu_options(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'menu_options_v1'").fetchone()
    if not exists:
        return
    conn.execute(
        """INSERT OR IGNORE INTO menu_options (date, recipe_id, reason, position)
           SELECT date, recipe_id, reason, position FROM menu_options_v1"""
    )
    conn.execute("DROP TABLE menu_options_v1")


def _migrate_plan_entries(conn):
    """Oudere databases hadden `plan_entries` met ontbijt/lunch/diner; neem het avondeten over."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'plan_entries'").fetchone()
    if not exists:
        return
    conn.execute(
        """INSERT OR IGNORE INTO dinner_choices (date, recipe_id, servings)
           SELECT date, recipe_id, servings FROM plan_entries WHERE slot = 'diner'"""
    )
    conn.execute(
        """INSERT OR IGNORE INTO menu_options (date, recipe_id)
           SELECT date, recipe_id FROM plan_entries WHERE slot = 'diner'"""
    )
    conn.execute("DROP TABLE plan_entries")


def _check_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Ongeldige datum: {value!r} (verwacht JJJJ-MM-DD)")


def _positive_int(value, default, label):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} moet een geheel getal zijn")
    if number <= 0:
        raise ValueError(f"{label} moet groter dan 0 zijn")
    return number


def _clean_recipe(data):
    if not isinstance(data, dict):
        raise ValueError("Recept moet een object zijn")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("Een recept heeft een naam nodig")

    prep = data.get("prep_minutes")
    prep = None if prep in (None, "") else _positive_int(prep, None, "Bereidingstijd")

    ingredients = []
    for ing in data.get("ingredients") or []:
        ing_name = str(ing.get("name") or "").strip()
        if not ing_name:
            continue
        qty = ing.get("quantity")
        if qty in (None, ""):
            qty = None
        else:
            try:
                qty = float(str(qty).replace(",", "."))
            except ValueError:
                raise ValueError(f"Ongeldige hoeveelheid voor {ing_name}: {qty!r}")
        ingredients.append({"name": ing_name, "quantity": qty, "unit": str(ing.get("unit") or "").strip()})

    return {
        "name": name,
        "servings": _positive_int(data.get("servings"), 2, "Aantal personen"),
        "prep_minutes": prep,
        "instructions": str(data.get("instructions") or "").strip(),
        "tags": str(data.get("tags") or "").strip(),
        "image": _clean_image(data.get("image")),
        "source_url": _clean_url(data.get("source_url")),
        "ingredients": ingredients,
    }
