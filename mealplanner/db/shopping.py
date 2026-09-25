"""Eén doorlopende boodschappenlijst, iconen en 'vaak gekocht'."""

from datetime import datetime, timezone

from ..groceries import (
    combine, display_name, format_amount, homemade_match, primary, product_key, recipe_key, shopping_product,
)
from .base import NotFound
from .cleaning import icon_key


class ShoppingMixin:
    def shopping_list(self):
        """De hele lijst: hetzelfde product (ook als het anders geschreven is) op één tegel, met een
        hoeveelheid om mee te winkelen (zie groceries.py)."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.*, r.name AS recipe FROM shopping_items s
                   LEFT JOIN recipes r ON r.id = s.source_recipe_id
                   ORDER BY s.id"""
            ).fetchall()
        groups = {}
        for row in rows:
            product, name = shopping_product(row["name"], row["unit"])
            key = f"{'bought' if row['checked'] else 'buy'}:{product}"
            item = groups.setdefault(key, {
                "key": key, "product": product, "name": name, "entries": [],
                "recipes": [], "checked": bool(row["checked"]), "manual": False,
            })
            item["entries"].append((row["quantity"], row["unit"]))
            if row["recipe"] and row["recipe"] not in item["recipes"]:
                item["recipes"].append(row["recipe"])
            if row["source_date"] is None:
                item["manual"] = True
        items = []
        for item in groups.values():
            totals = combine(item.pop("entries"), item["product"], canned=item["product"].endswith(" blik"))
            item["amount"] = format_amount(totals)
            item["quantity"], item["unit"] = primary(totals)
            items.append(item)
        return items

    def _group_rows(self, conn, key):
        state, _, product = key.partition(":")
        if state not in ("buy", "bought") or not product:
            raise NotFound("Dit product staat niet (meer) op de lijst")
        rows = [
            r for r in conn.execute(
                "SELECT id, name, unit FROM shopping_items WHERE checked = ? ORDER BY id", (int(state == "bought"),)
            )
            if shopping_product(r["name"], r["unit"])[0] == product
        ]
        if not rows:
            raise NotFound("Dit product staat niet (meer) op de lijst")
        return rows

    def update_shopping_item(self, key, name, quantity=None, unit=""):
        """Wijzig een product op de lijst (naam en hoeveelheid). Het wordt dan één eigen regel."""
        name = str(name or "").strip()[:80]
        if not name:
            raise ValueError("Geef het product een naam")
        if quantity not in (None, ""):
            try:
                quantity = round(float(str(quantity).replace(",", ".")), 2)
            except ValueError:
                raise ValueError("De hoeveelheid moet een getal zijn") from None
            if not 0 < quantity < 100000:
                raise ValueError("Kies een hoeveelheid groter dan 0")
        else:
            quantity = None
        unit = str(unit or "").strip().lower()[:20]
        if unit == "stuks":
            unit = ""
        with self.connect() as conn:
            ids = [r["id"] for r in self._group_rows(conn, key)]
            conn.execute(f"DELETE FROM shopping_items WHERE id IN ({','.join('?' * len(ids))})", ids)
            conn.execute(
                "INSERT INTO shopping_items (name, quantity, unit, checked) VALUES (?, ?, ?, ?)",
                (name, quantity, unit, int(key.startswith("bought:"))),
            )

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

    def add_ingredients_to_list(self, ingredients, recipe_id=None, servings=None):
        """Zet ingrediënten (al omgerekend naar het gewenste aantal personen) op de boodschappenlijst.
        Met een bewaard recept erbij zie je op de tegel voor welk recept het is. Iets wat je zelf maakt
        (zoals naan, als dat in je receptenboek staat) wordt vervangen door de ingrediënten daarvan."""
        rows = []
        for ing in ingredients:
            name = str(ing.get("name") or "").strip()[:80]
            if not name:
                continue
            quantity = ing.get("quantity")
            quantity = round(float(quantity), 2) if quantity not in (None, "") else None
            rows.append((name, quantity, str(ing.get("unit") or "").strip()[:20]))
        if not rows:
            raise ValueError("Dit recept heeft geen ingrediënten om op de lijst te zetten")
        with self.connect() as conn:
            if recipe_id is not None and not conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone():
                recipe_id = None
            expanded, homemade = self._expand_homemade(conn, rows, recipe_id, servings)
            conn.executemany(
                "INSERT INTO shopping_items (name, quantity, unit, source_recipe_id) VALUES (?, ?, ?, ?)",
                [(name, quantity, unit, source or recipe_id) for name, quantity, unit, source in expanded],
            )
        return {"added": len(expanded), "homemade": homemade}

    def _homemade_index(self, conn):
        """Eigen recepten op sleutel, om te herkennen wat je zelf maakt."""
        index = {}
        for row in conn.execute("SELECT id, name, servings FROM recipes"):
            key = recipe_key(row["name"])
            if len(key) >= 3:
                index.setdefault(key, dict(row))
        return index

    def homemade_parts(self, recipe):
        """Ingrediënten van dit recept die je zelf maakt: [{index, recipe_id, name}]."""
        with self.connect() as conn:
            index = self._homemade_index(conn)
        parts = []
        for i, ing in enumerate(recipe["ingredients"]):
            own = homemade_match(ing["name"], index)
            if own and own["id"] != recipe["id"]:
                parts.append({"index": i, "recipe_id": own["id"], "name": own["name"]})
        return parts

    def _expand_homemade(self, conn, rows, recipe_id=None, servings=None):
        """Vervang ingrediënten die je zelf maakt door de ingrediënten van dat eigen recept (één laag diep).
        Geeft ([(naam, hoeveelheid, eenheid, bron-recept of None)], [namen van zelfgemaakte recepten])."""
        index = self._homemade_index(conn)
        result, homemade = [], []
        for name, quantity, unit in rows:
            own = homemade_match(name, index)
            if own is None or own["id"] == recipe_id:
                result.append((name, quantity, unit, None))
                continue
            factor = (servings or own["servings"]) / own["servings"]
            for ing in conn.execute(
                "SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position", (own["id"],)
            ):
                amount = round(ing["quantity"] * factor, 2) if ing["quantity"] is not None else None
                result.append((ing["name"].strip(), amount, ing["unit"].strip(), own["id"]))
            if own["name"] not in homemade:
                homemade.append(own["name"])
        return result, homemade

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
        """Wat je vaak koopt, het meest waarschijnlijke eerst.

        Telt hoe vaak je iets gekocht hebt, en kijkt naar het ritme: koop je iets ongeveer elke week en is
        dat alweer een week geleden, dan komt het bovenaan (due). Wat je lang niet gekocht hebt, zakt."""
        with self.connect() as conn:
            counts = conn.execute("SELECT key, name, count, last_at FROM purchase_counts WHERE count > 0").fetchall()
            log = {}
            for row in conn.execute("SELECT key, bought_at FROM purchase_log ORDER BY bought_at"):
                log.setdefault(row["key"], []).append(_when(row["bought_at"]))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = []
        for row in counts:
            since = (now - _when(row["last_at"])).total_seconds() / 86400
            times = log.get(row["key"], [])
            due = None
            if len(times) >= 2:
                interval = (times[-1] - times[0]).total_seconds() / 86400 / (len(times) - 1)
                if interval >= 1:
                    due = since / interval
            score = row["count"] * (0.6 + min(due, 1.5) if due is not None else 1)
            if since > 60:
                score *= 0.4
            result.append({"name": display_name(row["name"]), "count": row["count"], "due": due is not None and due >= 0.85, "score": score})
        result.sort(key=lambda r: -r["score"])
        seen, unique = set(), []  # oudere tellingen kunnen nog onder een andere schrijfwijze staan
        for item in result:
            key = product_key(item["name"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:limit]

    def product_catalog(self, limit=400):
        """Namen om uit te kiezen bij het toevoegen: wat je ooit kocht en de ingrediënten van je recepten."""
        with self.connect() as conn:
            bought = [r["name"] for r in conn.execute("SELECT name FROM purchase_counts ORDER BY count DESC")]
            used = [r["name"] for r in conn.execute(
                "SELECT name, COUNT(*) AS n FROM ingredients GROUP BY lower(name) ORDER BY n DESC"
            )]
        seen, names = set(), []
        for name in [*bought, *used]:
            key = product_key(name)
            if key and key not in seen:
                seen.add(key)
                names.append(display_name(name))
        return names[:limit]

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
        name = display_name(name)
        key = product_key(name)
        if not key:
            return
        if delta > 0:
            conn.execute(
                """INSERT INTO purchase_counts (key, name, count) VALUES (?, ?, 1)
                   ON CONFLICT (key) DO UPDATE SET count = count + 1, name = excluded.name, last_at = datetime('now')""",
                (key, name),
            )
            conn.execute("INSERT INTO purchase_log (key) VALUES (?)", (key,))
        else:
            conn.execute("UPDATE purchase_counts SET count = MAX(count - 1, 0) WHERE key = ?", (key,))
            conn.execute(
                "DELETE FROM purchase_log WHERE id = (SELECT MAX(id) FROM purchase_log WHERE key = ?)", (key,)
            )


def _when(text):
    """Tijdstip uit SQLite (UTC, 'JJJJ-MM-DD UU:MM:SS')."""
    return datetime.fromisoformat(str(text).replace("T", " ")[:19])
