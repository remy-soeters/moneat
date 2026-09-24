# Mealplanner

Web-app voor het avondeten: stel per week een menu samen met per avond een paar opties
uit je eigen recepten, kies per avond wat je eet, en krijg automatisch een boodschappenlijst
voor de gekozen maaltijden. Claude vult elke komende avond aan tot 3 opties (instelbaar); nieuwe
recepten van Claude komen pas in je receptenboek als je ze kiest of bewaart.

- **Receptenboek:** schrijf recepten zelf, importeer ze via een link van een receptensite (inclusief foto)
  of laat Claude er een bedenken. Je kunt ook je eigen foto uploaden.
- **Inspiratie:** wat er deze maand in het seizoen is, en collecties van 6 recepten per thema
  (of zelf ingetypt) die je bewaart of direct op het menu zet.

Importeren leest het gestructureerde recept (schema.org/Recipe) dat vrijwel alle receptensites
publiceren; staat dat er niet, dan haalt Claude het recept uit de tekst van de pagina.

- **Backend:** Python 3.11+ (alleen standaardbibliotheek) met een JSON-API en SQLite
- **Frontend:** HTML, CSS en JavaScript zonder build-stap (`static/`)
- **AI:** Claude via de officiële `anthropic` Python SDK (optioneel)

## Installeren (eenmalig)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Starten

```bash
./start.sh
```

Open daarna http://127.0.0.1:8000 en voeg je Anthropic API-sleutel toe via **Instellingen**
(tandwiel rechtsboven). De database komt in `data/mealplanner.db`, foto's in `data/images/`.
Opties: `./start.sh --port 8080`, `--host 0.0.0.0` (bereikbaar op je netwerk), `--db pad/naar/bestand.db`.

Zonder `.venv` start de app ook met `python3 -m mealplanner.server`; alles werkt dan behalve de
functies met Claude.

De API-sleutel kun je invoeren in de app zelf via **Instellingen**; een sleutel die je daar opslaat
gaat voor op de omgevingsvariabele `ANTHROPIC_API_KEY`. Hij wordt bewaard in `data/mealplanner.db`
(niet in git) en daarna alleen gemaskeerd getoond.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
```

## Structuur

| Pad | Inhoud |
| --- | --- |
| `mealplanner/db.py` | SQLite-schema, recepten, weekmenu, boodschappenlijst |
| `mealplanner/server.py` | HTTP-server en API-routes |
| `mealplanner/ai.py` | Claude: menu-opties, recepten bedenken en uitlezen, inspiratie |
| `mealplanner/importer.py` | Recepten van websites importeren (schema.org/Recipe) |
| `mealplanner/images.py` | Opslag van receptfoto's |
| `static/` | Frontend |
| `tests/` | Unittests voor database en API |

## API

| Methode | Pad | Beschrijving |
| --- | --- | --- |
| GET/POST | `/api/recipes` | Recepten ophalen / aanmaken |
| GET/PUT/DELETE | `/api/recipes/{id}` | Eén recept |
| POST | `/api/recipes/import` | `{url}` → concept-recept van een website (niet opgeslagen) |
| POST | `/api/recipes/generate` | `{prompt, servings}` → concept-recept door Claude (niet opgeslagen) |
| POST | `/api/images` | Afbeelding (ruwe bytes) uploaden → `{image}` |
| GET/PUT | `/api/settings` | Instellingen lezen / `{api_key}` opslaan (sleutel komt alleen gemaskeerd terug) |
| DELETE | `/api/settings/api-key` | Opgeslagen sleutel verwijderen |
| POST | `/api/settings/test` | Verbinding met Claude testen (verbruikt geen tokens) |
| POST | `/api/inspiration` | `{theme, servings, refresh}` → collectie van 6 recepten (bewaard per thema) |
| GET | `/api/menu?week=JJJJ-MM-DD` | Opties en keuzes van de week (ma–zo) waarin die datum valt |
| POST | `/api/menu/options` | `{date, recipe_id}` eigen recept op het menu zetten |
| DELETE | `/api/menu/options/{id}` | Optie van het menu halen (en de keuze, als die het was) |
| POST | `/api/menu/options/{id}/choose` | `{servings}` deze optie kiezen (een voorstel wordt dan als recept bewaard) |
| POST | `/api/menu/options/{id}/save` | Voorstel van Claude bewaren in het receptenboek |
| DELETE | `/api/menu/choice?date=…` | Keuze ongedaan maken |
| POST | `/api/menu/copy-previous` | `{week}` opties van vorige week overnemen |
| POST | `/api/menu/fill` | `{week, wishes, servings, per_day}` Claude vult komende avonden zonder keuze aan tot `per_day` opties |
| GET | `/api/shopping?week=…` | Boodschappenlijst van de gekozen maaltijden, geschaald naar aantal personen |
| POST | `/api/shopping/check` | `{week, key, checked}` afvinken |
