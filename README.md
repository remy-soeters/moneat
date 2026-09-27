# MonEat

Web-app voor het avondeten van je huishouden.

- **Vandaag:** de startpagina toont groot wat je vanavond eet (met foto en recept); **Start met koken** opent
  het recept meteen in de kookmodus. Daaronder de komende dagen. Heb je gisteren iets gekozen en nog niet
  beoordeeld, dan vraagt hij hoe het was.
- **Plannen:** een stappenplan. "Wat wil je volgende week eten?", daarna per avond een paar opties van de AI.
  Tik op een gerecht om het te kiezen, vraag om **andere opties**, of kies **Anders…**: uit de vriezer, uit eten,
  afhalen, restjes of iets uit je receptenboek. Met **Zelf omschrijven** typ je waar je zin in hebt ("iets met de
  kip en spinazie die nog in de koelkast liggen, binnen 30 minuten"); de AI schrijft er een volledig recept bij, dat
  vooraan bij de opties van die avond komt. Swipe (of tik) door naar de volgende avond; aan het eind zie je
  je week. Nieuwe recepten van de AI komen pas in je receptenboek als je ze kiest of bewaart. Een gerecht staat
  maar één keer in de week op het menu, en wat je deze week al hebt weggeklikt of op een andere avond hebt laten
  liggen, komt die week niet terug. Bovenaan de week: **Zet op boodschappenlijst** (de ingrediënten van de
  gekozen avonden vanaf vandaag), **Wijzigen** (de avonden vanaf vandaag nog eens langslopen) en **Opnieuw
  beginnen** (keuzes en opties vanaf vandaag weghalen en opnieuw plannen; je receptenboek blijft zoals het is).
  In het weekoverzicht **sleep** je een avond naar een andere dag (aan de greep rechts, met de muis aan de hele rij,
  of op de telefoon door de rij even vast te houden): de twee avonden wisselen om, met hun opties en boodschappen.
  Met het toetsenbord kan het ook: pijltje omhoog of omlaag op de greep.
- **Receptenboek:** schrijf recepten zelf, importeer ze via een link van een receptensite (inclusief foto)
  of laat Claude er een bedenken (volledig uitgeschreven: voorbereiding, tijden, temperaturen, en elk ingrediënt
  gebruikt). Je kunt ook je eigen foto uploaden. Met een **hartje** maak je een recept
  favoriet (ieder voor zich); het filter *Favorieten* toont alleen die.
- **Een recept** opent als pagina met drie kolommen: foto en gegevens, ingrediënten (om te rekenen naar het
  aantal personen) en de bereiding. **Start met koken** zet de **kookmodus** aan: grotere letters, stappen en
  ingrediënten afvinken door erop te tikken, een kookwekker, en het scherm blijft aan. Na **Klaar met koken**
  geef je 1 tot 5 sterren, met een notitie voor de volgende keer ("meer knoflook"). De AI stelt favorieten
  en goed beoordeelde gerechten vaker voor, en slecht beoordeelde niet meer.
- **Eerst een impressie, daarna het volledige recept.** Swipekaarten, inspiratie en opties voor het weekmenu
  bedenkt de AI met vele tegelijk: een impressie om zin te krijgen (foto, een smakelijke zin, ingrediënten en een
  korte bereiding; de receptpagina zegt dat erbij). Bewaar of kies je er een, dan schrijft de AI het volledige
  recept op de achtergrond uit, met dezelfde naam, personen en foto; staat het op je boodschappenlijst, dan
  verandert die mee. Dat geldt ook voor kaarten en inspiratie die er al stonden. Heb je het recept intussen zelf gewijzigd, dan blijft jouw versie staan. Vind je een
  bestaand recept te summier, tik dan onder de bereiding op **Te kort? Laat … het uitgebreider uitschrijven**.
- **Recepten swipen** (op de inspiratiepagina): geef je voedselvoorkeuren op (dieet, keukens, tijd,
  liever niet) en swipe door gerechten met foto en korte omschrijving. Naar rechts bewaart het recept
  in je receptenboek, naar links slaat het over; gezien gerechten komen niet terug. Pas als je Swipen opent, zet
  de server een voorraad gerechten mét foto klaar (instelbaar: 5, 10, 15 of 20; niet al bij het opstarten van de
  app, zodat er geen foto's gemaakt worden die je nooit ziet). Terwijl je wacht, zie je een pan op het vuur, hoe ver
  het is (gerechten bedenken, foto's maken) en welke gerechten er straks aankomen.
- **Boodschappen:** één doorlopende lijst met tegels, in de secties *Kopen* en *Gekocht*.
  Met **Zet op boodschappenlijst** bij Plannen komen de ingrediënten van je gekozen avondeten erop (voor het
  gekozen aantal personen). Kies je daarna iets anders voor zo'n avond, dan verandert de lijst mee; wat je al
  gekocht hebt, blijft staan.
  Hetzelfde product is één tegel, ook als recepten het anders schrijven, met een hoeveelheid om mee te
  winkelen: "2 blikken" in plaats van "400 g + 1 blik", hele uien, en geen eetlepels olijfolie. Iets wat je zelf
  maakt (staat "Naan" in je receptenboek, dan is naanbrood in een ander recept dat recept) komt niet op de lijst:
  de ingrediënten ervan wel. Toevoegen gaat via de balk onderin: het veld blijft onderin, net boven het
  toetsenbord, met de suggesties erboven; eerst wat je volgens je koopritme waarschijnlijk weer nodig hebt.
  Typ je iets ("tom"), dan zie je wat je eerder kocht (tomaten, tomatenpuree, cherrytomaten), met wat speling
  ("tomaat" vindt ook "tomaten"); ingrediënten uit je recepten alleen als dat weinig oplevert. Tik de producten
  aan die je nodig hebt; je zoekwoord blijft staan, zodat je er meer kunt aantikken. Enter zet precies wat je
  typte op de lijst (of het bekende product, als je dat typte).
  Gemini tekent voor elk product één keer een icoon, en hergebruikt dat daarna: "tomaat", "tomaten" en "verse
  tomaten" delen er een (uit blik krijgt een eigen icoon). Wat nog nooit op je lijst stond, zoals gangbare
  boodschappen in de suggesties, krijgt pas een icoon als het erop komt. Houd een tegel ingedrukt om hem te wijzigen; daar kun je
  ook een **nieuw icoon** laten tekenen (eventueel met een beschrijving, zoals "een fles"), een eigen afbeelding
  kiezen of teruggaan naar de emoji.
- **Inspiratie:** wat er deze maand in het seizoen is, en collecties van 6 recepten per thema
  (of zelf ingetypt) die je bewaart of direct op het menu zet.

Importeren leest het gestructureerde recept (schema.org/Recipe) dat vrijwel alle receptensites
publiceren; staat dat er niet, dan haalt Claude het recept uit de tekst van de pagina.

Iedereen in het huishouden krijgt een **eigen login**, maar jullie delen het weekmenu, de recepten en de
boodschappenlijst. De site werkt op telefoon (ook als app op je beginscherm), iPad en laptop, met onderin
een zwevende menubalk. De vormgeving volgt het designsysteem "Organic": wit met groen als hoofdkleur en roze
als tweede kleur, letters Domine (koppen) en Figtree (tekst).

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
voeg je je API-sleutel(s) toe via **Instellingen** (onder het rondje met je initialen rechtsboven). De database komt in `data/mealplanner.db`, foto's in `data/images/`.
Opties: `./start.sh --port 8080`, `--host 0.0.0.0` (bereikbaar op je netwerk), `--db pad/naar/bestand.db`.

Zonder `.venv` start de app ook met `python3 -m mealplanner.server`; alles werkt dan behalve de
functies met Claude.

### Accounts en inloggen

- **Eerste keer:** zolang er nog geen account is, print de server bij het opstarten een eenmalige code,
  bijvoorbeeld `ABCD-1234` (in Docker: `docker compose logs mealplanner`). Met die code maak je in de app het
  eerste account aan; dat wordt de **beheerder**. Zo kan alleen iemand met toegang tot de server dat doen.
- **Huishouden:** de beheerder voegt bij **Instellingen → Huishouden** anderen toe. Iedereen deelt dezelfde
  recepten, het menu en de lijst. Alleen beheerders zien en wijzigen de AI-sleutels, modellen en accounts.
- **Wachtwoord vergeten:** een beheerder maakt bij Huishouden een nieuw wachtwoord aan. Ben je de enige
  beheerder, dan kan het op de server:

  ```bash
  docker compose exec mealplanner python -m mealplanner.users password remy
  ```

  Andere commando's: `python -m mealplanner.users list` en `python -m mealplanner.users add <naam> --admin`.

### AI: Claude en Gemini

In **Instellingen** (rondje rechtsboven) staat per onderwerp wat je kunt instellen, met de sleutel die erbij hoort:

- **Gemini** (Google): tekst (recepten, menu, inspiratie) is gratis met limieten, maar **alleen met een
  sleutel uit een Google-project zonder betaalgegevens**. Gemini maakt ook de **foto's en iconen**; die zijn
  niet gratis (Nano Banana 2 Lite kost ongeveer $0,03 per foto) en vragen een sleutel uit een project mét
  betalen. Vul daarom allebei in: de gratis bij **Slimme hulp (AI)**, de betaalde bij **Foto's en iconen**.
  Sleutels via https://aistudio.google.com/apikey.
- **Claude** (Anthropic): betaald, beste kwaliteit. Kies bij **Slimme hulp (AI)** Opus 5, Sonnet 5 of Haiku 4.5.
  Sleutel via https://console.anthropic.com.

Het beeldmodel kies je bij **Foto's en iconen**; foto's automatisch laten maken kun je daar ook uitzetten. Daar
staat ook het **verbruik** (beheerder) van de afgelopen 7 of 30 dagen: hoeveel foto's, iconen en tekstverzoeken er
gemaakt zijn, waarvoor (bijvoorbeeld "Iconen voor boodschappen" of "Menu-opties"), wat de app vanzelf deed zonder
dat iemand erom vroeg, hoeveel tekst via de gratis sleutel ging, en een geschat bedrag voor foto's en iconen.

### Foutmeldingen

Lukt iets niet, dan zegt de app in gewone taal wat er aan de hand is, bijvoorbeeld dat je Gemini-limiet per
minuut of per dag bereikt is, dat je tegoed op is of dat je voor foto's moet betalen. Bij **Instellingen →
Foutmeldingen** (beheerder) staat wat er de laatste tijd misging, met de precieze fout erbij: wat Gemini of Claude
letterlijk antwoordde, of dat de verbinding wegviel ("Failed to fetch" in de browser). Zulke verbindingsfouten
onthoudt de browser en stuurt hij naar het logboek zodra het weer lukt. Dezelfde regels staan ook in het
serverlog (`docker compose logs`).

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
- API-sleutels staan alleen in `data/` (niet in git) en worden nooit volledig teruggestuurd.

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
| `mealplanner/db/` | SQLite per onderdeel: recepten, menu, boodschappen, swipen, instellingen, beoordelingen, gebruikers |
| `mealplanner/users.py` | Accounts beheren vanaf de opdrachtregel |
| `mealplanner/netguard.py` | Veilig webpagina's ophalen voor de import (niet het eigen netwerk in) |
| `mealplanner/ai.py` | AI: menu-opties, recepten bedenken en uitlezen, inspiratie, foto's |
| `mealplanner/gemini.py` | Google Gemini (Interactions API) voor tekst en foto's |
| `mealplanner/importer.py` | Recepten van websites importeren (schema.org/Recipe) |
| `mealplanner/groceries.py` | Boodschappen samenvoegen: zelfde product, winkeleenheden (blikken, hele stuks), zelfgemaakte onderdelen |
| `mealplanner/images.py` | Opslag van receptfoto's |
| `mealplanner/preloader.py` | Houdt op de achtergrond swipekaarten mét foto klaar |
| `mealplanner/writer.py` | Schrijft op de achtergrond impressies van de AI volledig uit zodra ze in het receptenboek komen |
| `mealplanner/icons.py` | Laat Gemini op de achtergrond iconen voor producten tekenen |
| `static/index.html` | De pagina's en vensters |
| `static/css/` | Opmaak per onderdeel (pastel wit, groen als hoofdkleur, roze als tweede kleur) |
| `static/js/` | JavaScript-modules per onderdeel; `main.js` start de app, `nav.js` wisselt tussen de pagina's (die zich daar zelf aanmelden), `home.js` is Vandaag, `menu.js` Plannen (weekoverzicht met slepen), `journey.js` het stappenplan (met zelf omschrijven), `plan.js` wat die delen (keuzes, boodschappen), `view.js` de receptpagina, `cook.js` de kookmodus, `rating.js` sterren en hartjes |
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
| GET/POST | `/api/recipes` | Recepten ophalen (met jouw hartje en de gemiddelde sterren) / aanmaken |
| GET/PUT/DELETE | `/api/recipes/{id}` | Eén recept (GET met de laatste beoordelingen en notities; bij een impressie (`draft`) ook `writing`: wordt hij nu uitgeschreven?) |
| POST | `/api/recipes/{id}/write` | Recept (opnieuw) volledig laten uitschrijven door de AI; naam, personen en foto blijven |
| PUT | `/api/recipes/{id}/favorite` | `{favorite}` → hartje aan of uit (per gebruiker) |
| POST | `/api/recipes/{id}/rating` | `{stars, note, date}` → beoordeling na het koken (1 per gebruiker per dag) |
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
| GET | `/api/menu?week=JJJJ-MM-DD` | Opties en keuzes van de week (ma–zo) waarin die datum valt; `listed` per keuze: staan de boodschappen op de lijst? |
| POST | `/api/menu/options` | `{date, recipe_id}` eigen recept op het menu zetten |
| DELETE | `/api/menu/options/{id}` | Optie van het menu halen (en de keuze, als die het was) |
| POST | `/api/menu/options/{id}/choose` | `{servings}` deze optie kiezen (een voorstel wordt dan als recept bewaard) |
| POST | `/api/menu/options/{id}/save` | Voorstel van Claude bewaren in het receptenboek |
| DELETE | `/api/menu/choice?date=…` | Keuze (of bijzondere avond) ongedaan maken |
| POST | `/api/menu/to-list` | `{week, today}` boodschappen van de gekozen avonden (vanaf `today`) op de lijst zetten; daarna verandert de lijst mee met die avonden |
| POST | `/api/menu/reset` | `{week, today}` opnieuw beginnen: keuzes, bijzondere avonden, opties en niet-gekochte boodschappen vanaf `today` weghalen |
| POST | `/api/menu/fill` | `{week, dates?, wishes, servings, per_day}` de AI vult komende avonden zonder keuze aan tot `per_day` opties (optioneel alleen `dates`) |
| POST | `/api/menu/refresh` | `{date, per_day, servings, wishes}` "andere opties": nieuwe AI-opties voor één avond (de oude gaan pas weg als de nieuwe er zijn) |
| POST | `/api/menu/special` | `{date, kind}` avond zonder recept: `vriezer`, `uiteten`, `afhalen` of `restjes` |
| POST | `/api/menu/describe` | `{date, prompt, servings}` zelf omschrijven: de AI schrijft een volledig recept dat vooraan bij de opties van die avond komt → `{id}` |
| POST | `/api/menu/move` | `{from, to, today}` twee avonden (vanaf vandaag) omwisselen, met hun keuze, opties en boodschappen |
| GET | `/api/home?today=JJJJ-MM-DD` | Startpagina: vanavond en de komende 6 dagen, hoeveel er nog te halen is, en het avondeten van gisteren als je dat nog niet beoordeeld hebt |
| GET | `/api/shopping` | De hele boodschappenlijst (samengevoegd per product, met iconen) |
| POST | `/api/shopping/check` | `{key, checked}` product als gekocht markeren of terugzetten |
| POST | `/api/shopping/items` | `{text}` zelf iets toevoegen, bijv. "2 liter melk" |
| POST | `/api/shopping/recipe` | `{ingredients, recipe_id, servings}` ingrediënten van een recept op de lijst zetten (zelfgemaakte onderdelen vervangen door hun ingrediënten) |
| PUT | `/api/shopping/items` | `{key, name, quantity, unit}` product wijzigen |
| DELETE | `/api/shopping/items?key=…` | Product van de lijst halen |
| POST | `/api/shopping/clear-bought` | Alles wat gekocht is van de lijst halen |
| GET | `/api/shopping/suggestions` | Wat je waarschijnlijk nodig hebt (op koopritme), gangbare boodschappen, en alle bekende producten om in te zoeken (`bought`: eerder gekocht) |
| POST | `/api/shopping/icon` | `{name, hint}` Gemini tekent een nieuw icoon voor een product (eventueel naar een beschrijving) |
| PUT | `/api/shopping/icon` | `{name, image}` eigen afbeelding als icoon (eerst uploaden via `/api/images`), of `""` voor de emoji |
| GET | `/api/usage?days=7` | Verbruik van de AI per dag en per doel, met geschat bedrag (beheerder) |
| GET/DELETE | `/api/errors` | Foutmeldingen bekijken / wissen (beheerder) |
| POST | `/api/errors` | `{errors: [{method, path, message, detail, at}]}` fouten die de browser zag maar de server niet (geen verbinding, time-out) |
| GET | `/api/health` | Controle of de server draait (voor Docker) |
