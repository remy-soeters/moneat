"""Accounts van het huishouden en hun ingelogde apparaten (sessies)."""

import re
import sqlite3

from .base import NotFound

USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,31}")
PUBLIC_FIELDS = "id, username, display_name, is_admin, created_at"


def clean_username(value):
    username = str(value or "").strip().lower()
    if not USERNAME.fullmatch(username):
        raise ValueError("Een gebruikersnaam heeft 2 tot 32 tekens: kleine letters, cijfers, punt, streepje of liggend streepje")
    return username


def _user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
    }


class UsersMixin:
    # ---------- accounts ----------

    def count_users(self):
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def list_users(self):
        with self.connect() as conn:
            rows = conn.execute(f"SELECT {PUBLIC_FIELDS} FROM users ORDER BY username").fetchall()
        return [_user(r) for r in rows]

    def get_user(self, user_id):
        with self.connect() as conn:
            row = conn.execute(f"SELECT {PUBLIC_FIELDS} FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFound("Deze gebruiker bestaat niet")
        return _user(row)

    def credentials(self, username):
        """(gebruiker, wachtwoord-hash) voor inloggen, of (None, None) als de naam onbekend is."""
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {PUBLIC_FIELDS}, password_hash FROM users WHERE username = ?", (str(username or "").strip().lower(),)
            ).fetchone()
        return (_user(row), row["password_hash"]) if row else (None, None)

    def password_hash(self, user_id):
        with self.connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFound("Deze gebruiker bestaat niet")
        return row["password_hash"]

    def create_user(self, username, password_hash, display_name="", is_admin=False):
        username = clean_username(username)
        display_name = str(display_name or "").strip()[:60] or username
        try:
            with self.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                    (username, display_name, password_hash, int(bool(is_admin))),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"De gebruikersnaam ‘{username}’ bestaat al") from None
        return self.get_user(cur.lastrowid)

    def set_password_hash(self, user_id, password_hash):
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = datetime('now') WHERE id = ?",
                (password_hash, user_id),
            )
        if cur.rowcount == 0:
            raise NotFound("Deze gebruiker bestaat niet")

    def update_user(self, user_id, display_name=None, is_admin=None):
        user = self.get_user(user_id)
        if is_admin is False and user["is_admin"] and self._admin_count() <= 1:
            raise ValueError("Er moet minstens één beheerder overblijven")
        with self.connect() as conn:
            if display_name is not None:
                name = str(display_name).strip()[:60] or user["username"]
                conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
            if is_admin is not None:
                conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(bool(is_admin)), user_id))
        return self.get_user(user_id)

    def delete_user(self, user_id):
        user = self.get_user(user_id)
        if user["is_admin"] and self._admin_count() <= 1:
            raise ValueError("Je kunt de laatste beheerder niet verwijderen")
        with self.connect() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def _admin_count(self):
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]

    # ---------- sessies ----------

    def create_session(self, token_hash, user_id, expires_at, user_agent=""):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, user_agent) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, expires_at, str(user_agent or "")[:200]),
            )

    def session_user(self, token_hash):
        """(gebruiker, laatst gezien) voor een geldige sessie, of (None, None)."""
        with self.connect() as conn:
            row = conn.execute(
                f"""SELECT {", ".join("u." + f.strip() for f in PUBLIC_FIELDS.split(","))}, s.last_seen_at
                    FROM sessions s JOIN users u ON u.id = s.user_id
                    WHERE s.token_hash = ? AND s.expires_at > datetime('now')""",
                (token_hash,),
            ).fetchone()
        return (_user(row), row["last_seen_at"]) if row else (None, None)

    def extend_session(self, token_hash, expires_at):
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen_at = datetime('now'), expires_at = ? WHERE token_hash = ?",
                (expires_at, token_hash),
            )

    def delete_session(self, token_hash):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def delete_user_sessions(self, user_id, keep=None):
        """Log een gebruiker overal uit, behalve (optioneel) op het huidige apparaat."""
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash IS NOT ?", (user_id, keep))

    def session_count(self, user_id):
        with self.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE user_id = ? AND expires_at > datetime('now')", (user_id,)
            ).fetchone()[0]
