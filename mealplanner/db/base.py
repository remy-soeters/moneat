"""Verbinding met SQLite, en het aanmaken en bijwerken van de tabellen."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .schema import migrate


class NotFound(Exception):
    pass


class BaseDatabase:
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
            if migrate(conn):
                # Nieuwe of net omgezette lijst: zet het gekozen avondeten vanaf vandaag er één keer op.
                for row in conn.execute("SELECT date FROM dinner_choices WHERE date >= date('now')").fetchall():
                    self._sync_dinner_to_list(row["date"], conn)

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

