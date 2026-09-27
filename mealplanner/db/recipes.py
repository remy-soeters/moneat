"""Recepten en hun ingrediënten."""

from .base import NotFound
from .cleaning import clean_image, clean_recipe


class RecipesMixin:
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
        recipe = clean_recipe(data)
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO recipes (name, servings, prep_minutes, instructions, tags, image, source_url, draft)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (recipe["name"], recipe["servings"], recipe["prep_minutes"], recipe["instructions"], recipe["tags"],
                 recipe["image"], recipe["source_url"], int(recipe["draft"])),
            )
            self._replace_ingredients(conn, cur.lastrowid, recipe["ingredients"])
            recipe_id = cur.lastrowid
        return self.get_recipe(recipe_id)

    def update_recipe(self, recipe_id, data):
        recipe = clean_recipe(data)
        with self.connect() as conn:
            cur = conn.execute(
                """UPDATE recipes SET name = ?, servings = ?, prep_minutes = ?, instructions = ?, tags = ?,
                                      image = ?, source_url = ?, draft = ?
                   WHERE id = ?""",
                (recipe["name"], recipe["servings"], recipe["prep_minutes"], recipe["instructions"], recipe["tags"],
                 recipe["image"], recipe["source_url"], int(recipe["draft"]), recipe_id),
            )
            if cur.rowcount == 0:
                raise NotFound(f"Recept {recipe_id} bestaat niet")
            self._replace_ingredients(conn, recipe_id, recipe["ingredients"])
            days = [r["date"] for r in conn.execute("SELECT date FROM dinner_choices WHERE recipe_id = ?", (recipe_id,))]
        for day in days:  # gewijzigde ingrediënten ook op de boodschappenlijst doorvoeren
            self._sync_dinner_to_list(day)
        return self.get_recipe(recipe_id)

    def set_recipe_image(self, recipe_id, image):
        """Alleen de foto van een recept vervangen; de rest (die intussen uitgeschreven kan zijn) blijft zoals hij is."""
        with self.connect() as conn:
            if conn.execute("UPDATE recipes SET image = ? WHERE id = ?", (clean_image(image), recipe_id)).rowcount == 0:
                raise NotFound(f"Recept {recipe_id} bestaat niet")
        return self.get_recipe(recipe_id)

    def draft_recipe_ids(self):
        """Recepten die nog een schets van de AI zijn, de oudste eerst."""
        with self.connect() as conn:
            return [r["id"] for r in conn.execute("SELECT id FROM recipes WHERE draft = 1 ORDER BY id")]

    def save_written_recipe(self, recipe_id, before, written, force=False):
        """Bewaar de volledig uitgeschreven versie van een recept. Naam, aantal personen, foto en bron blijven zoals
        ze waren. Is het recept intussen zelf gewijzigd (vergeleken met `before`), dan blijft dat staan, tenzij
        `force`. Geeft het bewaarde recept terug, of None als het niet meer nodig was."""
        current = self.get_recipe(recipe_id)
        fields = ("name", "servings", "instructions", "ingredients", "draft")
        if not force and any(current[f] != before[f] for f in fields):
            return None
        return self.update_recipe(recipe_id, {
            **written,
            "name": current["name"],
            "servings": current["servings"],
            "tags": written.get("tags") or current["tags"],
            "image": current["image"],
            "source_url": current["source_url"],
            "draft": False,
        })

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
        recipe["draft"] = bool(recipe["draft"])
        recipe["ingredients"] = [
            {"name": r["name"], "quantity": r["quantity"], "unit": r["unit"]}
            for r in conn.execute(
                "SELECT name, quantity, unit FROM ingredients WHERE recipe_id = ? ORDER BY position", (row["id"],)
            )
        ]
        return recipe
