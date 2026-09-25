"""Instellingen, bewaarde inspiratie en het opruimen van afbeeldingen."""

import json
from datetime import date


class SettingsMixin:
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
