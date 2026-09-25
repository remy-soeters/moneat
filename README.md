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
- **Inspiratie:** wat er deze maand in het seizoen is, en collecties van 6 recepten per thema
  (of zelf ingetypt) die je bewaart of direct op het menu zet.

Importeren leest het gestructureerde recept (schema.org/Recipe) dat vrijwel alle receptensites
publiceren; staat dat er niet, dan haalt Claude het recept uit de tekst van de pagina.

Iedereen in het huishouden krijgt een **eigen login**, maar jullie delen het weekmenu, de recepten en de
boodschappenlijst. De site werkt op telefoon (menubalk onderin, ook als app op je beginscherm), iPad en laptop.

- **Backend:** Python 3.11+ (alleen standaardbibliotheek) met een JSON-API en SQLite
- **Frontend:** HTML, CSS en JavaScript-modules zonder build-stap (`static/`)
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

Open daarna http://127.0.0.1:8000. De eerste keer maak je daar je eigen account aan (zie hieronder) en
voeg je je API-sleutel(s) toe via **Instellingen**. De database komt in `data/mealplanner.db`, foto's in `data/images/`.
Opties: `./start.sh --port 8080`, `--host 0.0.0.0` (bereikbaar op je netwerk), `--db pad/naar/bestand.db`.

Zonder `.venv` start de app ook met `python3 -m mealplanner.server`; alles werkt dan behalve de
functies met Claude.

### Accounts en inloggen

- **Eerste keer:** zolang er nog geen account is, print de server bij het opstarten een eenmalige code,
  bijvoorbeeld `ABCD-1234` (in Docker: `docker compose logs mealplanner`). Met die code maak je in de app het
  eerste account aan; dat wordt de **beheerder**. Zo kan alleen iemand met toegang tot de server dat doen.
- **Huishouden:** de beheerder voegt bij **Instellingen → Huishouden** anderen toe. Iedereen deelt dezelfde
  recepten, het menu en de lijst. Alleen beheerders zien en wijzigen de AI-sleutels, modellen, Bring! en accounts.
- **Wachtwoord vergeten:** een beheerder maakt bij Huishouden een nieuw wachtwoord aan. Ben je de enige
  beheerder, dan kan het op de server:

  ```bash
  docker compose exec mealplanner python -m mealplanner.users password remy
  ```

  Andere commando's: `python -m mealplanner.users list` en `python -m mealplanner.users add <naam> --admin`.

### AI: Claude en Gemini

In **Instellingen** in het menu kies je wie de recepten schrijft en voeg je de API-sleutels toe:

- **Gemini** (Google): tekst (recepten, menu, inspiratie) is gratis met limieten, maar **alleen met een
  sleutel uit een Google-project zonder betaalgegevens**. Gemini maakt ook de **foto's en iconen**; die zijn
  niet gratis (Nano Banana 2 Lite kost ongeveer $0,03 per foto) en vragen een sleutel uit een project mét
  betalen. Vul daarom bij Instellingen → Sleutels allebei in: de betaalde voor foto's, de gratis voor tekst.
  Sleutels via https://aistudio.google.com/apikey.
- **Claude** (Anthropic): betaald, beste kwaliteit. Kies Opus 5, Sonnet 5 of Haiku 4.5. Sleutel via
  https://console.anthropic.com.

Tekst- en beeldmodellen kies je bij Instellingen; foto's automatisch laten maken kun je daar ook uitzetten.

### Bring!

Bij Instellingen → Boodschappen koppel je de Bring!-app (inloggen met je Bring!-account; het wachtwoord
wordt niet bewaard). Daarna stuurt de knop **Naar Bring! sturen** bij Boodschappen alles onder "Kopen" naar
je Bring!-lijst. Bring! heeft geen officiële API; de koppeling werkt zoals de Bring!-app zelf en kan
stoppen als Bring! iets verandert.

Sleutels worden bewaard in `data/mealplanner.db` (niet in git) en daarna alleen gemaskeerd getoond. Een
sleutel in de app gaat voor op de omgevingsvariabelen `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`.

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

**Op je thuisnetwerk.** Standaard is de app alleen op de computer zelf bereikbaar. Maak naast
`docker-compose.yml` een bestand `.env` en start opnieuw:

```
MEALPLANNER_ADRES=0.0.0.0
MEALPLANNER_POORT=8090
```

Open dan `http://<ip-adres-van-de-server>:8090` en log in.

### Op internet, via Nginx Proxy Manager

Zo is de app van buitenaf bereikbaar via een eigen adres met HTTPS, bijvoorbeeld `https://eten.jouwdomein.nl`.

1. Zet in `.env` ook `MEALPLANNER_PROXY=1` en start opnieuw (`docker compose up -d`). Dan weet de app dat hij
   achter een proxy staat: cookies worden alleen via HTTPS verstuurd en de rem op wachtwoorden raden kijkt naar
   het echte IP-adres van de bezoeker.
2. Laat bij je domeinregistrar een DNS-record (A) voor bijvoorbeeld `eten.jouwdomein.nl` naar je thuis-IP wijzen.
3. In Nginx Proxy Manager: **Hosts → Proxy Hosts → Add Proxy Host**
   - Domain Names: `eten.jouwdomein.nl`
   - Scheme `http`, Forward Hostname/IP: het IP van de server (bijv. `192.168.1.2`), Forward Port: `8090`
   - Zet **Block Common Exploits** aan.
   - Tabblad **SSL**: *Request a new SSL Certificate*, en zet **Force SSL**, **HTTP/2** en **HSTS** aan.
4. In je router staan alleen poort 80 en 443 open naar Nginx Proxy Manager, **niet** poort 8090.

### Beveiliging

- Alles behalve het inlogscherm vraagt om een login; ook de foto's.
- Wachtwoorden worden met **scrypt** gehasht; sessies zijn willekeurige sleutels in een HttpOnly-cookie
  (`SameSite=Lax`, via HTTPS ook `Secure` met het `__Host-`-voorvoegsel). In de database staat alleen een hash.
- Na 5 mislukte pogingen worden een IP-adres en een gebruikersnaam 15 minuten geblokkeerd.
- Wijzigingen via de API moeten een eigen kop meesturen en van dezelfde site komen (bescherming tegen CSRF).
- Strikte beveiligingskoppen: Content-Security-Policy zonder inline scripts, `X-Frame-Options: DENY`, `nosniff`,
  HSTS via HTTPS.
- De recepten-import haalt alleen openbare websites op (poort 80/443) en nooit adressen op je eigen netwerk,
  zoals je router of Home Assistant; dat wordt ook bij doorverwijzingen gecontroleerd.
- De container draait als gewone gebruiker, met een alleen-lezen bestandssysteem (behalve `/data`) en zonder extra rechten.
- API-sleutels en Bring!-gegevens staan alleen in `data/` (niet in git) en worden nooit volledig teruggestuurd.

**Naar een andere computer verhuizen.** Haal de code op met `git clone`, kopieer de map `data/` mee
(daarin staan ook je API-sleutels en accounts; die staan bewust niet in git) en start met `docker compose up -d --build`.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
```

## Structuur

| Pad | Inhoud |
| --- | --- |
| `mealplanner/server.py` | Opstarten (`python -m mealplanner.server`) |
| `mealplanner/app.py` | De webapp: inloggen controleren, routes uitvoeren, beveiligingskoppen |
| `mealplanner/web.py` | Klein webframework: verzoeken, antwoorden, routes |
| `mealplanner/auth.py` | Wachtwoorden (scrypt), sessies en de rem op raden |
| `mealplanner/routes/` | API per onderdeel: account, recepten, menu, inspiratie, swipen, boodschappen, instellingen |
| `mealplanner/db/` | SQLite per onderdeel: recepten, menu, boodschappen, swipen, instellingen, gebruikers |
| `mealplanner/users.py` | Accounts beheren vanaf de opdrachtregel |
| `mealplanner/netguard.py` | Veilig webpagina's ophalen voor de import (niet het eigen netwerk in) |
| `mealplanner/ai.py` | AI: menu-opties, recepten bedenken en uitlezen, inspiratie, foto's |
| `mealplanner/gemini.py` | Google Gemini (Interactions API) voor tekst en foto's |
| `mealplanner/bring.py` | Koppeling met de Bring!-boodschappenapp |
| `mealplanner/importer.py` | Recepten van websites importeren (schema.org/Recipe) |
| `mealplanner/images.py` | Opslag van receptfoto's |
| `mealplanner/preloader.py` | Houdt op de achtergrond swipekaarten mét foto klaar |
| `mealplanner/icons.py` | Laat Gemini op de achtergrond iconen voor producten tekenen |
| `static/index.html` | De pagina's en vensters |
| `static/css/` | Opmaak per onderdeel (pastel wit, roze en mint) |
| `static/js/` | JavaScript-modules per onderdeel; `main.js` start de app |
| `tests/` | Unittests; `tests/helpers.py` start een testserver met een ingelogde gebruiker |

## API

Alle paden behalve `/api/auth/status`, `/api/auth/login`, `/api/auth/setup` en `/api/health` vragen om een
login (sessie-cookie). Verzoeken die iets wijzigen moeten de kop `X-Requested-With: mealplanner` meesturen.

| Methode | Pad | Beschrijving |
| --- | --- | --- |
| GET | `/api/auth/status` | Ingelogd? Wie? Moet het eerste account nog gemaakt worden? |
| POST | `/api/auth/setup` | `{code, username, display_name, password}` eerste account (beheerder) |
| POST | `/api/auth/login` / `/api/auth/logout` | `{username, password}` in- en uitloggen |
| PUT | `/api/auth/password` | `{current, new}` eigen wachtwoord wijzigen (logt andere apparaten uit) |
| PUT | `/api/auth/profile` | `{display_name}` eigen naam wijzigen |
| POST | `/api/auth/logout-others` | Uitloggen op alle andere apparaten |
| GET/POST | `/api/users` | Accounts bekijken / toevoegen (beheerder) |
| PUT/DELETE | `/api/users/{id}` | `{display_name, is_admin, password}` wijzigen / account verwijderen (beheerder) |
| GET/POST | `/api/recipes` | Recepten ophalen / aanmaken |
| GET/PUT/DELETE | `/api/recipes/{id}` | Eén recept |
| POST | `/api/recipes/import` | `{url}` → concept-recept van een website (niet opgeslagen) |
| POST | `/api/recipes/generate` | `{prompt, servings}` → concept-recept door Claude (niet opgeslagen) |
| POST | `/api/images` | Afbeelding (ruwe bytes) uploaden → `{image}` |
| GET/PUT | `/api/settings` | Instellingen lezen / opslaan (opslaan alleen beheerder): sleutels, `text_provider`, modellen |
| DELETE | `/api/settings/key/{claude\|gemini\|gemini_text}` | Opgeslagen sleutel verwijderen (beheerder) |
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
| POST | `/api/shopping/recipe` | `{ingredients, recipe_id}` ingrediënten van een recept op de lijst zetten |
| DELETE | `/api/shopping/items?key=…` | Product van de lijst halen |
| POST | `/api/shopping/clear-bought` | Alles wat gekocht is van de lijst halen |
| GET | `/api/shopping/suggestions` | Vaak gekochte producten (aangevuld met gangbare boodschappen) |
| POST | `/api/bring/sync` | Alles onder "Kopen" naar Bring! sturen |
| POST/DELETE | `/api/bring/login`, `/api/bring` | Bring! koppelen / ontkoppelen (beheerder) |
| GET | `/api/health` | Controle of de server draait (voor Docker) |
