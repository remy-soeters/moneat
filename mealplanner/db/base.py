"""Verbinding met SQLite, en het aanmaken en bijwerken van de tabellen."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .schema import (
    SCHEMA,
    USERS_SCHEMA,
    _add_missing_recipe_columns,
    _migrate_old_menu_options,
    _migrate_plan_entries,
    _migrate_week_shopping,
    _rename_old_menu_options,
)


class NotFound(Exception):
    pass


class BaseDatabase:
    _pending_list_migration = False

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        # Een geheugendatabase (tests) deelt één verbinding; laat threads die om de beurt gebruiken.
        self._memory_lock = threading.RLock()
        with self.connect() as conn:
            if self._memory_conn is None:
                # WAL: lezen en schrijven tegelijk (meerdere mensen in het huishouden) zonder op elkaar te wachten.
                conn.execute("PRAGMA journal_mode = WAL")
            had_list = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopping_items'"
            ).fetchone() is not None
            _rename_old_menu_options(conn)
            _add_missing_recipe_columns(conn)
            conn.executescript(SCHEMA)
            conn.executescript(USERS_SCHEMA)
            _migrate_old_menu_options(conn)
            _migrate_plan_entries(conn)
            if _migrate_week_shopping(conn) or not had_list:
                self._pending_list_migration = True
        self._finish_migrations()

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
