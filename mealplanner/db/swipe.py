"""Kaarten om recepten te swipen."""

import json

from .base import NotFound
from .cleaning import clean_recipe


class SwipeMixin:
    def add_swipe_cards(self, ideas):
        """Voeg nieuwe kaarten toe (dicts met recipe en description); dubbele namen worden overgeslagen."""
        seen = {name.lower() for name in self.known_dish_names()}
        added = 0
        with self.connect() as conn:
            for idea in ideas:
                recipe = clean_recipe(idea["recipe"])
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


def _card(row):
    return {
        "id": row["id"],
        "recipe": json.loads(row["recipe"]),
        "description": row["description"],
        "image": row["image"],
        "status": row["status"],
        "recipe_id": row["recipe_id"],
    }
