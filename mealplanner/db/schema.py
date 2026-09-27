"""Tabellen en omzettingen van oudere databases."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    servings      INTEGER NOT NULL DEFAULT 2 CHECK (servings > 0),
    prep_minutes  INTEGER,
    instructions  TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '',
    image         TEXT NOT NULL DEFAULT '',
    source_url    TEXT NOT NULL DEFAULT '',
    -- 1 = een korte schets van de AI (bedacht met vele tegelijk) die nog volledig uitgeschreven wordt (writer.py)
    draft         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingredients (
    id         INTEGER PRIMARY KEY,
    recipe_id  INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL,
    quantity   REAL,
    unit       TEXT NOT NULL DEFAULT ''
);

-- Opties op het weekmenu: per avond een paar gerechten waaruit je kiest. Een optie is een eigen
-- recept (recipe_id) of een voorstel van Claude dat nog niet in het receptenboek staat (suggestion).
CREATE TABLE IF NOT EXISTS menu_options (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    recipe_id   INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
    suggestion  TEXT,
    source      TEXT NOT NULL DEFAULT 'eigen' CHECK (source IN ('eigen', 'claude')),
    reason      TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    CHECK ((recipe_id IS NULL) <> (suggestion IS NULL)),
    UNIQUE (date, recipe_id)
);

-- De gekozen maaltijd per avond.
CREATE TABLE IF NOT EXISTS dinner_choices (
    date       TEXT PRIMARY KEY,
    recipe_id  INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    servings   INTEGER NOT NULL CHECK (servings > 0)
);

-- Avonden zonder recept: uit de vriezer, uit eten, afhalen of restjes. Sluit een gekozen recept uit.
CREATE TABLE IF NOT EXISTS special_dinners (
    date  TEXT PRIMARY KEY,
    kind  TEXT NOT NULL,
    note  TEXT NOT NULL DEFAULT ''
);

-- Avonden waarvan de boodschappen op de lijst gezet zijn ("Zet op boodschappenlijst"). Verandert het eten
-- van zo'n avond, dan verandert de lijst mee; kiezen voor een andere avond laat de lijst met rust.
CREATE TABLE IF NOT EXISTS listed_days (
    date  TEXT PRIMARY KEY
);

-- Bewaarde inspiratie van Claude, zodat een thema niet elke keer opnieuw gegenereerd hoeft te worden.
CREATE TABLE IF NOT EXISTS inspiration (
    key         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    payload     TEXT NOT NULL
);

-- Kaarten om te swipen: voorstellen die je bewaart (naar rechts) of overslaat (naar links).
CREATE TABLE IF NOT EXISTS swipe_cards (
    id           INTEGER PRIMARY KEY,
    recipe       TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    image        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'liked', 'skipped')),
    recipe_id    INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    swiped_at    TEXT
);

-- Gerechten die deze week al voorbijkwamen en niet gekozen zijn ("andere opties"): die komen niet terug.
CREATE TABLE IF NOT EXISTS passed_dishes (
    week        TEXT NOT NULL,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (week, name)
);

-- Wanneer iets gekocht is, om te voorspellen wat je binnenkort weer nodig hebt.
CREATE TABLE IF NOT EXISTS purchase_log (
    id         INTEGER PRIMARY KEY,
    key        TEXT NOT NULL,
    bought_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS purchase_log_key ON purchase_log(key);

-- Instellingen van de app, zoals de Anthropic API-sleutel.
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Eén doorlopende boodschappenlijst. Regels komen van een gekozen avondeten (source_date + recipe)
-- of zijn zelf toegevoegd (geen bron). Gelijke producten worden in de weergave samengevoegd.
CREATE TABLE IF NOT EXISTS shopping_items (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    quantity          REAL,
    unit              TEXT NOT NULL DEFAULT '',
    checked           INTEGER NOT NULL DEFAULT 0,
    source_date       TEXT,
    source_recipe_id  INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Wat er misging: de melding die je zag en de precieze fout (bijv. het antwoord van Gemini). Zie db/errors.py.
CREATE TABLE IF NOT EXISTS error_log (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source      TEXT NOT NULL,
    action      TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    user        TEXT NOT NULL DEFAULT '',
    count       INTEGER NOT NULL DEFAULT 1
);

-- Iconen per product (door Gemini getekend), één keer gemaakt en daarna hergebruikt.
CREATE TABLE IF NOT EXISTS product_icons (
    key    TEXT PRIMARY KEY,
    image  TEXT NOT NULL
);

-- Hoe vaak iets gekocht is, voor de suggesties "vaak gekocht".
CREATE TABLE IF NOT EXISTS purchase_counts (
    key      TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    last_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

"""

USERS_SCHEMA = """
-- Accounts van het huishouden. Iedereen deelt dezelfde recepten, menu en lijst.
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY,
    username             TEXT NOT NULL UNIQUE,
    display_name         TEXT NOT NULL DEFAULT '',
    password_hash        TEXT NOT NULL,
    is_admin             INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    password_changed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ingelogde apparaten. We bewaren alleen een hash van de sessiesleutel, nooit de sleutel zelf.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at    TEXT NOT NULL,
    user_agent    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

-- Favorieten (het hartje): per persoon.
CREATE TABLE IF NOT EXISTS favorites (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id   INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, recipe_id)
);

-- Beoordelingen na het koken: 1 tot 5 sterren per persoon per keer dat het gegeten is.
CREATE TABLE IF NOT EXISTS ratings (
    id          INTEGER PRIMARY KEY,
    recipe_id   INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    stars       INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    note        TEXT NOT NULL DEFAULT '',
    cooked_on   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (recipe_id, user_id, cooked_on)
);
CREATE INDEX IF NOT EXISTS ratings_recipe ON ratings(recipe_id);
"""


def migrate(conn):
    """Maak ontbrekende tabellen aan en zet een oudere database om. Elke stap kijkt zelf of hij nodig is,
    dus dit draait gewoon bij elke start. Geeft True als de boodschappenlijst nieuw is (of net omgezet):
    dan moet het gekozen avondeten er nog op."""
    had_list = _has_table(conn, "shopping_items")
    had_listed_days = _has_table(conn, "listed_days")
    _rename_old_menu_options(conn)
    _add_missing_recipe_columns(conn)
    conn.executescript(SCHEMA)
    conn.executescript(USERS_SCHEMA)
    _migrate_old_menu_options(conn)
    _migrate_plan_entries(conn)
    if not had_listed_days:
        _mark_chosen_dinners_listed(conn)
    # De koppeling met Bring! is uit de app gehaald: gooi de bewaarde inlog (tokens) en sync-gegevens weg.
    conn.execute("DELETE FROM settings WHERE key IN ('bring_auth', 'bring_synced')")
    return _migrate_week_shopping(conn) or not had_list


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _add_missing_recipe_columns(conn):
    """Oudere databases hebben nog geen kolommen voor foto, bron en schets."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(recipes)")]
    if not columns:
        return
    added = {"image": "TEXT NOT NULL DEFAULT ''", "source_url": "TEXT NOT NULL DEFAULT ''", "draft": "INTEGER NOT NULL DEFAULT 0"}
    for column, definition in added.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} {definition}")


def _migrate_week_shopping(conn):
    """Eerdere versie had een lijst per week. Zet zelf toegevoegde producten over; geeft True als er omgezet is."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(shopping_items)")]
    if "week_start" not in columns:
        return False
    conn.execute("ALTER TABLE shopping_items RENAME TO shopping_items_week")
    conn.executescript(SCHEMA)
    conn.execute(
        """INSERT INTO shopping_items (name, quantity, unit, checked, created_at)
           SELECT name, quantity, unit, checked, created_at FROM shopping_items_week"""
    )
    conn.execute("DROP TABLE shopping_items_week")
    return True


def _rename_old_menu_options(conn):
    """De eerste versie van menu_options had geen id-kolom; zet die tabel opzij om over te nemen."""
    columns = [r[1] for r in conn.execute("PRAGMA table_info(menu_options)")]
    if columns and "id" not in columns:
        conn.execute("ALTER TABLE menu_options RENAME TO menu_options_v1")


def _migrate_old_menu_options(conn):
    if not _has_table(conn, "menu_options_v1"):
        return
    conn.execute(
        """INSERT OR IGNORE INTO menu_options (date, recipe_id, reason, position)
           SELECT date, recipe_id, reason, position FROM menu_options_v1"""
    )
    conn.execute("DROP TABLE menu_options_v1")


def _mark_chosen_dinners_listed(conn):
    """Vroeger kwam elk gekozen avondeten vanzelf op de boodschappenlijst: die avonden staan er dus al op."""
    conn.execute("INSERT OR IGNORE INTO listed_days (date) SELECT date FROM dinner_choices")


def _migrate_plan_entries(conn):
    """Oudere databases hadden `plan_entries` met ontbijt/lunch/diner; neem het avondeten over."""
    if not _has_table(conn, "plan_entries"):
        return
    conn.execute(
        """INSERT OR IGNORE INTO dinner_choices (date, recipe_id, servings)
           SELECT date, recipe_id, servings FROM plan_entries WHERE slot = 'diner'"""
    )
    conn.execute(
        """INSERT OR IGNORE INTO menu_options (date, recipe_id)
           SELECT date, recipe_id FROM plan_entries WHERE slot = 'diner'"""
    )
    conn.execute("DROP TABLE plan_entries")
