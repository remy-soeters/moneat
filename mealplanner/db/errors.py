"""Logboek van wat er misging (AI, server, browser), om terug te lezen bij Instellingen → Foutmeldingen."""

MAX_ENTRIES = 200


class ErrorLogMixin:
    def log_error(self, source, action, message, detail="", user="", when=None):
        """Bewaar een fout. Is het dezelfde als de vorige, dan telt die ene regel op in plaats van een nieuwe."""
        row = (str(source)[:40], str(action)[:120], str(message)[:1000], str(detail)[:4000], str(user or "")[:80])
        with self.connect() as conn:
            last = conn.execute(
                "SELECT id, source, action, message, detail, user FROM error_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last and tuple(last)[1:] == row:
                conn.execute(
                    "UPDATE error_log SET count = count + 1, created_at = COALESCE(?, datetime('now')) WHERE id = ?",
                    (when, last["id"]),
                )
                return
            conn.execute(
                """INSERT INTO error_log (source, action, message, detail, user, created_at)
                   VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')))""",
                (*row, when),
            )
            conn.execute("DELETE FROM error_log WHERE id <= (SELECT MAX(id) FROM error_log) - ?", (MAX_ENTRIES,))

    def recent_errors(self, limit=MAX_ENTRIES):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, source, action, message, detail, user, count FROM error_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_errors(self):
        with self.connect() as conn:
            conn.execute("DELETE FROM error_log")
