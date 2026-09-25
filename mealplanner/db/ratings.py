"""Favorieten (per persoon) en beoordelingen na het koken."""

from .cleaning import check_date


class RatingsMixin:
    def set_favorite(self, user_id, recipe_id, favorite):
        self.get_recipe(recipe_id)
        with self.connect() as conn:
            if favorite:
                conn.execute("INSERT OR IGNORE INTO favorites (user_id, recipe_id) VALUES (?, ?)", (user_id, recipe_id))
            else:
                conn.execute("DELETE FROM favorites WHERE user_id = ? AND recipe_id = ?", (user_id, recipe_id))

    def rate_recipe(self, recipe_id, user_id, stars, cooked_on, note=""):
        """Sla een beoordeling op (of werk die van dezelfde dag bij)."""
        self.get_recipe(recipe_id)
        check_date(cooked_on)
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            raise ValueError("Kies 1 tot 5 sterren") from None
        if not 1 <= stars <= 5:
            raise ValueError("Kies 1 tot 5 sterren")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO ratings (recipe_id, user_id, stars, note, cooked_on) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (recipe_id, user_id, cooked_on) DO UPDATE SET stars = excluded.stars, note = excluded.note""",
                (recipe_id, user_id, stars, str(note or "").strip()[:500], cooked_on),
            )

    def recipe_marks(self, user_id):
        """Per recept: {favorite, rating (gemiddelde), rating_count, my_rating} voor deze gebruiker."""
        with self.connect() as conn:
            favorites = {r[0] for r in conn.execute("SELECT recipe_id FROM favorites WHERE user_id = ?", (user_id,))}
            averages = {
                r["recipe_id"]: (r["avg"], r["n"])
                for r in conn.execute("SELECT recipe_id, AVG(stars) AS avg, COUNT(*) AS n FROM ratings GROUP BY recipe_id")
            }
            mine = {
                r["recipe_id"]: r["stars"]
                for r in conn.execute(
                    """SELECT recipe_id, stars FROM ratings r1 WHERE user_id = ? AND cooked_on =
                       (SELECT MAX(cooked_on) FROM ratings r2 WHERE r2.recipe_id = r1.recipe_id AND r2.user_id = r1.user_id)""",
                    (user_id,),
                )
            }
        return favorites, averages, mine

    def recipe_ratings(self, recipe_id, limit=10):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.stars, r.note, r.cooked_on, COALESCE(u.display_name, 'Iemand') AS name
                   FROM ratings r LEFT JOIN users u ON u.id = r.user_id
                   WHERE r.recipe_id = ? ORDER BY r.cooked_on DESC, r.id DESC LIMIT ?""",
                (recipe_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def unrated_dinner(self, user_id, day):
        """Het gekozen avondeten van `day`, als deze gebruiker het nog niet beoordeeld heeft."""
        check_date(day)
        with self.connect() as conn:
            row = conn.execute(
                """SELECT c.recipe_id FROM dinner_choices c
                   WHERE c.date = ? AND NOT EXISTS (
                       SELECT 1 FROM ratings r WHERE r.recipe_id = c.recipe_id AND r.user_id = ? AND r.cooked_on = c.date)""",
                (day, user_id),
            ).fetchone()
        return self.get_recipe(row["recipe_id"]) if row else None
