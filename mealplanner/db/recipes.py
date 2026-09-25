"""Recepten en hun ingrediënten."""

from .base import NotFound
from .cleaning import clean_recipe


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
                """INSERT INTO recipes (name, servings, prep_minutes, instructions, tags, image, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (recipe["name"], recipe["servings"], recipe["prep_minutes"], recipe["instructions"], recipe["tags"],
                 recipe["image"], recipe["source_url"]),
            )
            self._replace_ingredients(conn, cur.lastrowid, recipe["ingredients"])
            recipe_id = cur.lastrowid
        return self.get_recipe(recipe_id)

    def update_recipe(self, recipe_id, data):
        recipe = clean_recipe(data)
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
