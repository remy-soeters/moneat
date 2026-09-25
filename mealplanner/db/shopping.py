"""Eén doorlopende boodschappenlijst, iconen en 'vaak gekocht'."""

from .base import NotFound
from .cleaning import icon_key


class ShoppingMixin:
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

    def add_ingredients_to_list(self, ingredients, recipe_id=None):
        """Zet ingrediënten (al omgerekend naar het gewenste aantal personen) op de boodschappenlijst.
        Met een bewaard recept erbij zie je op de tegel voor welk recept het is."""
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
            conn.executemany(
                "INSERT INTO shopping_items (name, quantity, unit, source_recipe_id) VALUES (?, ?, ?, ?)",
                [(*row, recipe_id) for row in rows],
            )
        return len(rows)

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
