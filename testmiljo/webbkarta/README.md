# Planmosaik i en webbkarta: testmiljö

Visar alla antagna detaljplaner och planer med laga kraft sida vid sida i en webbkarta (Origo), ritade som en plankarta
(planområdesgräns, användningsytor i Boverkets färger, egenskapsmönster som prickmark och korsmark, användnings- och
egenskapsgränser), med data direkt ur plandatabasen i PostGIS. Samma karta publiceras på tre sätt, med två karttjänster, så att de kan jämföras:

| Lager i kartan | Tjänst | Protokoll |
|---|---|---|
| GeoServer (WMS) | GeoServer 3.0 | bild (WMS), vektorer (WFS) |
| GeoServer (vektorrutor) | GeoServer 3.0 med tillägget vectortiles | vektorrutor (MVT), ritas i webbläsaren |
| QGIS Server (WMS) | QGIS Server 4.2 | bild (WMS), vektorer (WFS) |

Det här är en **testmiljö** och en mall för kommuner som vill göra något liknande. Den är inte en del av pluginet.

## Hur det hänger ihop

```
Rita Detaljplan ──checka in──▶ PostGIS: schemat med planerna (till exempel detaljplaner)
                                       │  vyn publicering.planmosaik (bara antagna och laga kraft)
                                       ▼  rollen karta_ro, bara läsrätt på vyn
                          ┌────────────┴────────────┐
                      GeoServer                 QGIS Server
                  (WMS + vektorrutor)               (WMS)
                          └────────────┬────────────┘
                                  nginx (behållaren web)  ──  Origo (statiska filer)
                                       │
                         värdens nginx: https://server/planmosaik/
```

- **Pluginets tabeller rörs aldrig.** Tjänsterna läser vyer i ett eget schema, `publicering`. Vyerna bestämmer vilka
  planer som är offentliga (här: *antagen* och *laga kraft*) och förbereder det en plankarta behöver:
  `plan_anvandning` (ytor med färg), `plan_egenskap` (ytor med mönster) och `plan_gransar` (gränslinjer i planens
  hierarki). `planmosaik` är planområdena med plandata (status, genomförandetid) och bestämmer vilka planer som visas.
- **Läsrollen `karta_ro`** kommer bara åt schemat `publicering`. Den kan inte skriva och inte läsa planernas egna tabeller.
- Kartan visar en plan så fort den har checkats in i databasen. Det behövs ingen export.

## Filerna

| Fil | Vad den gör |
|---|---|
| `skapa_testschema.py` | Gör SQL för ett testschema med fem demoplaner (olika status) från en GeoPackage. Behövs bara om du saknar planer i databasen. |
| `publicering.sql` | Publiceringsvyerna. Körs med planschemats namn och koordinatsystem som variabler (se nedan). |
| `publicering_roll.sh` | Skapar läsrollen `karta_ro` med slumpat lösenord i `.env`. |
| `forbered.sh` | Slumpar GeoServers adminlösenord och skriver `qgis/pg_service.conf` ur `.env`. |
| `docker-compose.yml` | De tre behållarna: GeoServer, QGIS Server och nginx. |
| `stil.py` | Planens utseende på ett ställe: mått för gränslinjer och mönster vid olika kartskalor (se "Skala" nedan). |
| `geoserver/` | `konfigurera_geoserver.py` (REST-anrop: lager, lagergrupp och stilar), `bygg_stilar.py` (skriver de skalberoende stilarna ur `stil.py`) och stilarna `plan_*.sld`. |
| `qgis/skapa_qgis_projekt.py` | Skapar QGIS-projektet som QGIS Server publicerar, ritat enligt `stil.py`. |
| `web/nginx.conf` | Vidarebefordran till de två karttjänsterna. GeoServers administration släpps inte ut. |
| `web/html/` | Origo-kartan: `index.json` (innehållet), `planmosaik.js` (planens stil för vektorrutorna), `index.html`. |
| `hamta_origo.sh` | Hämtar Origos färdiga filer (`js/`, `css/`, `img/`) från GitHub. |
| `nginx-host/` | Lägger till och tar bort `/planmosaik/` i värdens nginx (kräver sudo). |

## Sätta upp

Kräver Docker med Compose och en PostGIS-databas som tjänsterna når över ett Docker-nätverk. I compose-filen heter
nätverket `postgis_default` och databasen `postgis`. Ändra dem om er miljö ser annorlunda ut. Databasen måste släppa in
anslutningar från behållarna, och här kräver den SSL (`sslmode=require` är satt överallt).

1. **Databasen.** Som databasens ägare:
   `psql -v ON_ERROR_STOP=1 -v plan_schema=detaljplaner -v srid=3006 -f publicering.sql` (planschemats namn och
   koordinatsystemets EPSG-kod), sedan `sh publicering_roll.sh`.
2. **Hemligheter och filer.** `sh forbered.sh`
3. **Origo.** `sh hamta_origo.sh`. Skriver inte över `index.html`, `index.json` eller `planmosaik.js`.
4. **QGIS-projektet.** Kopiera `stil.py` till `qgis/` (behållaren ser bara den mappen). Kommandot står överst i
   `qgis/skapa_qgis_projekt.py` (ange EPSG-koden sist).
5. **Starta.** `docker compose up -d`, sedan `python3 geoserver/konfigurera_geoserver.py`.
6. **Publicera.** `sudo sh nginx-host/installera.sh` lägger in `/planmosaik/` i värdens nginx (säkerhetskopia, `nginx -t`
   och automatisk återställning om det misslyckas).

GeoServers administration når du bara via SSH-tunnel: `ssh -L 8081:127.0.0.1:8081 server`, sedan
`http://localhost:8081/geoserver/web/` (användare `admin`, lösenordet står i `.env`).

## Ta bort allt

```sh
sudo sh nginx-host/ta_bort.sh
docker compose down -v          # behållarna och GeoServers data
```

I databasen: `DROP SCHEMA publicering CASCADE; DROP ROLE karta_ro;` (och `DROP SCHEMA detaljplaner_test CASCADE;` om
du skapade testschemat). Radera sedan mappen.

## Skala

Linjer och mönster har **fast referensskala 1:1000**, som i Rita Detaljplan: mått anges vid den skalan och blir
proportionellt mindre när man zoomar ut, i stället för att ligga kvar i samma pixelbredd och täcka planen. En skärm har en
minsta pixelstorlek, så två saker skiljer från en plankarta på papper:

- En linje blir aldrig smalare än sin minsta bredd (planområdesgränsen 1 px), och streckmönstret byts mot en heldragen
  linje när luckorna blir för små.
- Gränser och mönster som blivit för små ritas inte alls: egenskapsgränser försvinner vid ungefär 1:6000,
  användningsgränser vid 1:12000 och mönster (prickmark, korsmark) vid 1:3300. Kvar blir färgen och planområdesgränsen.

Skalan delas i band och alla varianterna räknar likadant (`stil.py`; Origo-stilen i `web/html/planmosaik.js` har
samma tal i en tabell: ändra båda). GeoServers stilar skrivs om med `python geoserver/bygg_stilar.py` och
`python3 geoserver/konfigurera_geoserver.py`. QGIS-projektet byggs om med skriptet i `qgis/`.

## Bild eller vektor?

GeoServer och QGIS Server visas här som **WMS**, det vill säga färdiga bilder. Det är det vanligaste hos kommuner och det
som QGIS Desktop och de flesta kartor kan läsa. Bilder ritas på servern, så stilen (färg, mönster, streckmönster) blir
likadan överallt och webbläsaren behöver inget göra. Vektoralternativen:

| Alternativ | Vad det ger | Mindre bra |
|---|---|---|
| **WFS** (båda tjänsterna) | Geometri och attribut som GeoJSON. Stilen sätts i webbläsaren. | Hela lagret skickas, utan indelning i rutor. Bra för några hundra planer, sedan tungt. |
| **OGC API Features** (QGIS Server; GeoServer med tillägg) | Som WFS, men enklare och modernare. | Samma som WFS. Origo 2.10 har ingen färdig lagertyp för det. |
| **Vektorrutor** (GeoServer med tillägget vectortiles; Martin och pg_tileserv direkt ur databasen) | Små rutor som webbläsaren ritar. Skarpt vid alla zoomnivåer och tar lite av servern. | Stilen måste skrivas om för webbläsaren (här `planmosaik.js`), mönster blir enklare. |

Vektorrutor från GeoServer är vektoralternativet i den här miljön, och det som skalar bäst när antalet planer växer. Det
kräver tillägget `vectortiles` (`INSTALL_EXTENSIONS` och `STABLE_EXTENSIONS` i compose-filen: det hämtas från GeoServers
officiella nedladdningar vid första starten, 2,2 MB) och att cachen (GeoWebCache) får formatet
`application/vnd.mapbox-vector-tile` för lagergruppen. `konfigurera_geoserver.py` gör det. Rutorna kommer ur cachen och
förnyas efter en minut, så en ny incheckning syns snart.

## Det här lärde vi oss

- **Koordinatsystem.** Planerna ligger i SWEREF 99 (här EPSG:3008), men webbkartan går i EPSG:3857 så att OpenStreetMap
  och vektorrutorna (GeoServers cache har rutnätet EPSG:900913) passar. GeoServer och QGIS Server omprojicerar själva.
  Vill du ha kartan i SWEREF 99 kräver Origo `proj4Defs` och ett eget rutnät, och vektorrutorna går då inte att visa.
- **Hopp vid zoomning (Origo).** Origos exempelkonfiguration har avrundade upplösningar (`9.5546` i stället för
  `9.554628535647…`). Vektorrutor placeras av rutnätet, så felet växer med rutnummer och zoomnivå (flera hundra meter vid
  zoomnivå 17) och planerna flyttar sig när man zoomar. Använd exakta värden: `156543.03392804097 / 2^zoom`.
- **Databasanslutningar.** GeoServer tar upp till 10 anslutningar och QGIS Server några, så en roll med ont om anslutningar
  räcker inte. Sätt `max connections` (GeoServer) och en gräns på rollen, annars blir det `too many connections`. (Martin tar
  20 som standard, och var det som fyllde gränsen när det ingick.)
- **Informationsruta vid klick (Origo).**
  - `featureinfoLayer` på ett WMS-lager ska peka på **ett annat lager i `index.json`**, inte på ett lagernamn i tjänsten. Här
    är det två osynliga WMS-lager (`planmosaik_info_geoserver` och `planmosaik_info_qgis`, grupp `none`) som frågar
    `plan_anvandning`. Pekar man på något som inte finns händer ingenting alls, utan fel.
  - Vektorrutor kan Origo 2.10 rita men inte fråga: en träff på en yta i en vektorruta ger felet `getGeometryName is not a
    function`, eftersom ytorna (RenderFeature) saknar metoden. `planmosaik.js` lägger till den första gången en yta ritas.
    Det är en lagning av Origo, inte en funktion: provas efter varje Origo-uppdatering.
  - Datum som `date` får ett `Z` efter sig i GeoServers svar. Vyn skickar dem som text.
- **Utbredning i GeoServer.** Cachen (vektorrutorna) ger 404 för rutor utanför lagergruppens utbredning, och den räknas ut
  första gången. Läggs en plan utanför den ritas den inte, och rutnätet ser ut att sakna rutor. Ange kommunens utbredning
  i `EXTENT` i `konfigurera_geoserver.py` (körs om, tömmer cachen).
- **Origo.**
  - Det färdiga bygget saknar tillägget `olms` (MapLibre-stilar). Därför har vektorrutorna en egen stil i `planmosaik.js`.
  - `extent` i `index.json` måste vara hela projektionens utbredning. Origo bygger rutnätet av den.
  - Vektorrutor behöver ett eget rutnät på lagret (`tileGrid`): kvadratisk utbredning, exakta upplösningar och origo
    uppe till vänster (`alignBottomLeft: false`). Då blir Origos `{-y}` precis TMS-raden nerifrån som GeoServers cache vill ha.
    Med origo nere till vänster räknas raderna åt fel håll och alla rutor ger 404.
  - Vektorlagret byggs av Origo som `<källa><layerName>@<gridset>@<format>/{z}/{x}/{-y}.<format>`, alltså
    `gwc/service/tms/1.0.0/planmosaik:planmosaik_karta@EPSG:900913@pbf/...`. Rutor utanför planernas utbredning ger 404
    (det är ofarligt).
  - npm-paketet `origo` är något helt annat. Hämta från `github.com/origo-map/origo`.
- **QGIS Server.** WMS-lagrets namn är lagrets namn i projektet: kalla lagren som vyerna, annars fungerar inte
  `LAYERS=plan_anvandning`. Behållarens FastCGI-processer ärver inte miljövariabeln `PGSERVICEFILE`. Lägg tjänstefilen på
  `/etc/postgresql-common/pg_service.conf`. Då hamnar lösenordet aldrig i projektfilen.
  QGIS skriver färger som `#AARRGGBB`, inte `#RRGGBBAA`.
- **GeoServer.** Vyer saknar primärnyckel i databasen. Det fungerar, men GeoServer varnar. Etiketterna kan upprepas när
  Origo hämtar kartan i rutor.
- **Minne.** Hela miljön tog ungefär 1 GB (GeoServer 600 MB, QGIS Server 230 MB, nginx 15 MB). Sätt
  minnesgränser (görs i compose-filen) om servern delas med annat.
- **Delad planområdesgräns.** Ligger två planer kant i kant ritas planområdesgränsen mellan dem en gång. Vyn `plan_gransar`
  lägger ihop alla planers gränser (`ST_Union` med 5 cm rutnät, så att små avvikelser mellan två planers hörn inte ger två
  linjer) och tar bort användnings- och egenskapsgränser som ligger på den. Testplanerna `demo_dp_01` till `03` ligger så,
  se `skapa_testschema.py`.
- **Texter.** Planbeteckningar ritas inte i den här kartan. Vektorrutorna skulle kunna ha dem (webbläsaren ritar dem), men
  det kräver att stilen har en text.
