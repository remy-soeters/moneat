# Mealplanner

Web-app voor het avondeten: stel per week een menu samen met per avond een paar opties
uit je eigen recepten, kies per avond wat je eet, en krijg automatisch een boodschappenlijst
voor de gekozen maaltijden. Claude vult elke komende avond aan tot 3 opties (instelbaar); nieuwe
recepten van Claude komen pas in je receptenboek als je ze kiest of bewaart.

- **Receptenboek:** schrijf recepten zelf, importeer ze via een link van een receptensite (inclusief foto)
  of laat Claude er een bedenken. Je kunt ook je eigen foto uploaden.
- **Recepten swipen** (op de inspiratiepagina): geef je voedselvoorkeuren op (dieet, keukens, tijd,
  liever niet) en swipe door gerechten met foto en korte omschrijving. Naar rechts bewaart het recept
  in je receptenboek, naar links slaat het over; gezien gerechten komen niet terug. De server zet op de
  achtergrond een voorraad gerechten mét foto klaar (instelbaar: 5, 10, 15 of 20), zodat je niet hoeft te wachten.
- **Boodschappen:** één doorlopende lijst met tegels (zoals Bring!), in de secties *Kopen* en *Gekocht*.
  Kies je een avondeten, dan komen de ingrediënten er vanzelf op (voor het gekozen aantal personen);
  gelijke producten worden één tegel. Zelf iets toevoegen kan met suggesties van wat je vaak koopt, en
  Gemini tekent voor elk product één keer een icoon.
- **Bring!-sync** (optioneel): koppel je Bring!-account bij **Instellingen** en je boodschappen gaan vanzelf
  naar een Bring!-lijst naar keuze, met de hoeveelheid erbij. Vink je iets af in Bring!, dan komt het hier bij
  *Gekocht*; wat je in Bring! zelf toevoegt blijft daar staan.
- **Inspiratie:** wat er deze maand in het seizoen is, en collecties van 6 recepten per thema
  (of zelf ingetypt) die je bewaart of direct op het menu zet.

Importeren leest het gestructureerde recept (schema.org/Recipe) dat vrijwel alle receptensites
publiceren; staat dat er niet, dan haalt Claude het recept uit de tekst van de pagina.

- **Backend:** Python 3.11+ (alleen standaardbibliotheek) met een JSON-API en SQLite
- **Frontend:** HTML, CSS en JavaScript zonder build-stap (`static/`)
- **AI:** Claude (officiële `anthropic` SDK) of Google Gemini (REST); beide optioneel

## Installeren (eenmalig)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Starten

```bash
./start.sh
```

Open daarna http://127.0.0.1:8000 en voeg je API-sleutel(s) toe via **Instellingen** in het menu.
De database komt in `data/mealplanner.db`, foto's in `data/images/`.
Opties: `./start.sh --port 8080`, `--host 0.0.0.0` (bereikbaar op je netwerk), `--db pad/naar/bestand.db`.

Zonder `.venv` start de app ook met `python3 -m mealplanner.server`; alles werkt dan behalve de
functies met Claude.

### AI: Claude en Gemini

In **Instellingen** in het menu kies je wie de recepten schrijft en voeg je de API-sleutels toe:

- **Gemini** (Google): recepten schrijven is gratis met limieten (`gemini-3.8-flash`). Gemini maakt ook
  de **foto's** bij recepten (`gemini-3.1-flash-image`); dat is bij Google niet gratis, daarvoor moet je
  betalen instellen in AI Studio. Sleutel via https://aistudio.google.com/apikey.
- **Claude** (Anthropic): betaald, beste kwaliteit. Sleutel via https://console.anthropic.com.

Sleutels worden bewaard in `data/mealplanner.db` (niet in git) en daarna alleen gemaskeerd getoond. Een
sleutel in de app gaat voor op de omgevingsvariabelen `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`. De Gemini-modellen
kun je in de instellingen aanpassen als Google nieuwe versies uitbrengt.

### Bring!

Bij **Instellingen → Bring!** log je in met het e-mailadres en wachtwoord van je Bring!-account (heb je je
aangemeld met Google of Apple, stel dan eerst een wachtwoord in in de Bring!-app). De app kiest je
standaardlijst; een andere lijst kies je daar ook. Daarna gaat het vanzelf:

- Alles onder *Kopen* staat op de Bring!-lijst. Bekende producten krijgen de Bring!-naam (en het icoon),
  bijvoorbeeld *Melk* of *Uien*; de hoeveelheid (bijv. `500 g + 2 el`) staat eronder.
- Koop je iets hier of haal je het van de lijst, dan gaat het in Bring! naar *Recent* of eraf.
- Vink je iets af in Bring!, dan staat het hier bij *Gekocht* (de app kijkt elke twee minuten, en meteen als
  je de boodschappenlijst opent).
- Wat je in Bring! zelf toevoegt, raakt de app niet aan.

Bring! heeft geen officiële API; de app gebruikt dezelfde API als de Bring!-apps (zoals de Home
Assistant-integratie). Je e-mailadres en wachtwoord staan in `data/mealplanner.db`, net als de API-sleutels.

## Docker

De app kan ook als container draaien; hij start dan vanzelf weer na een herstart van de computer.

```bash
docker compose up -d --build
```

Open daarna http://127.0.0.1:8000. Je gegevens (database, foto's, iconen, API-sleutels) staan in de
map `data/` naast dit bestand; de container gebruikt die map, dus je bestaande recepten en lijst blijven.

- Stoppen: `docker compose down` (je gegevens blijven in `data/`)
- Na een update van de code: opnieuw `docker compose up -d --build`
- Meldingen van de server bekijken: `docker compose logs -f`

**Op je thuisnetwerk (bijv. een server thuis of je telefoon).** Standaard is de app alleen op de
computer zelf bereikbaar. Maak naast `docker-compose.yml` een bestand `.env` met deze regel en start opnieuw:

```
MEALPLANNER_ADRES=0.0.0.0
```

Open dan `http://<ip-adres-van-de-server>:8000`. Is poort 8000 al bezet door iets anders, voeg dan
bijvoorbeeld `MEALPLANNER_POORT=8080` toe aan `.env` en gebruik die poort in het adres. De app heeft geen wachtwoord: iedereen op je netwerk kan
je recepten aanpassen en de AI (op jouw kosten) gebruiken. Zet poort 8000 dus nooit open naar internet.

**Naar een andere computer verhuizen.** Haal de code op met `git clone`, kopieer de map `data/` mee
(daarin staan ook je API-sleutels; die staan bewust niet in git) en start met `docker compose up -d --build`.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
```

## Structuur

| Pad | Inhoud |
| --- | --- |
| `mealplanner/db.py` | SQLite-schema, recepten, weekmenu, boodschappenlijst |
| `mealplanner/server.py` | HTTP-server en API-routes |
| `mealplanner/ai.py` | AI: menu-opties, recepten bedenken en uitlezen, inspiratie, foto's |
| `mealplanner/gemini.py` | Google Gemini (Interactions API) voor tekst en foto's |
| `mealplanner/importer.py` | Recepten van websites importeren (schema.org/Recipe) |
| `mealplanner/images.py` | Opslag van receptfoto's |
| `mealplanner/preloader.py` | Houdt op de achtergrond swipekaarten mét foto klaar |
| `mealplanner/icons.py` | Laat Gemini op de achtergrond iconen voor producten tekenen |
| `mealplanner/bring.py` | Boodschappenlijst synchroniseren met Bring! |
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
| GET/PUT | `/api/settings` | Instellingen lezen / opslaan: `claude_api_key`, `gemini_api_key`, `text_provider`, Gemini-modellen |
| DELETE | `/api/settings/key/{claude\|gemini}` | Opgeslagen sleutel verwijderen |
| POST | `/api/settings/test` | `{provider}` verbinding met Claude of Gemini testen (verbruikt niets) |
| POST | `/api/recipes/{id}/photo` | Foto maken met Gemini voor een recept |
| POST | `/api/photos/draft` | `{recipe}` foto maken voor een recept dat nog niet bewaard is |
| POST | `/api/inspiration/photo` | `{theme, servings, index}` foto maken voor een inspiratie-idee |
| GET/PUT | `/api/preferences` | Voedselvoorkeuren voor swipen (`diet`, `cuisines`, `max_minutes`, `avoid`) |
| GET | `/api/swipe` | Kaarten die nog geswipet moeten worden, statistieken en voorkeuren |
| POST | `/api/swipe/more` | `{count, servings}` nieuwe kaarten laten maken door de AI |
| POST | `/api/swipe/cards/{id}` | `{liked}` swipen; bij `true` komt het recept (met foto) in het receptenboek |
| POST | `/api/swipe/cards/{id}/photo` | Foto maken voor een kaart (Gemini) |
| POST | `/api/swipe/undo` | Laatste swipe terugdraaien |
| POST | `/api/swipe/preload` | `{servings, retry}` voorraad op de achtergrond aanvullen; geeft de status terug |
| DELETE | `/api/swipe/pending` | Nog niet geswipete kaarten weggooien (na nieuwe voorkeuren) |
| POST | `/api/inspiration` | `{theme, servings, refresh}` → collectie van 6 recepten (bewaard per thema) |
| GET | `/api/menu?week=JJJJ-MM-DD` | Opties en keuzes van de week (ma–zo) waarin die datum valt |
| POST | `/api/menu/options` | `{date, recipe_id}` eigen recept op het menu zetten |
| DELETE | `/api/menu/options/{id}` | Optie van het menu halen (en de keuze, als die het was) |
| POST | `/api/menu/options/{id}/choose` | `{servings}` deze optie kiezen (een voorstel wordt dan als recept bewaard) |
| POST | `/api/menu/options/{id}/save` | Voorstel van Claude bewaren in het receptenboek |
| DELETE | `/api/menu/choice?date=…` | Keuze ongedaan maken |
| POST | `/api/menu/copy-previous` | `{week}` opties van vorige week overnemen |
| POST | `/api/menu/fill` | `{week, wishes, servings, per_day}` Claude vult komende avonden zonder keuze aan tot `per_day` opties |
| GET | `/api/shopping` | De hele boodschappenlijst (samengevoegd per product, met iconen) |
| POST | `/api/shopping/check` | `{key, checked}` product als gekocht markeren of terugzetten |
| POST | `/api/shopping/items` | `{text}` zelf iets toevoegen, bijv. "2 liter melk" |
| DELETE | `/api/shopping/items?key=…` | Product van de lijst halen |
| POST | `/api/shopping/clear-bought` | Alles wat gekocht is van de lijst halen |
| GET | `/api/shopping/suggestions` | Vaak gekochte producten (aangevuld met gangbare boodschappen) |
| GET | `/api/bring` | Status van de koppeling met Bring! |
| POST | `/api/bring/connect` | `{email, password}` inloggen bij Bring! en de standaardlijst kiezen; geeft ook `lists` |
| GET | `/api/bring/lists` | De lijsten in je Bring!-account |
| PUT | `/api/bring/list` | `{list_uuid}` naar een andere Bring!-lijst synchroniseren |
| POST | `/api/bring/sync` | Nu synchroniseren; geeft de boodschappenlijst terug (met `changed`) |
| DELETE | `/api/bring` | Bring! ontkoppelen (wat in Bring! staat blijft staan) |
