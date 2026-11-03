# Planmosaik i en webbkarta: testmiljö

Visar alla antagna detaljplaner och planer med laga kraft sida vid sida i en webbkarta (Origo), ritade som en plankarta
(planområdesgräns, användningsytor i Boverkets färger, egenskapsmönster som prickmark och korsmark, användnings- och
egenskapsgränser), med data direkt ur plandatabasen i PostGIS. Samma karta publiceras på tre sätt, så att de kan jämföras:

| Lager i kartan | Tjänst | Protokoll |
|---|---|---|
| GeoServer (WMS) | GeoServer 3.0 | bild (WMS), vektorer (WFS) |
| QGIS Server (WMS) | QGIS Server 4.2 | bild (WMS), vektorer (WFS) |
| Martin (vektorrutor) | Martin 1.14 | vektorrutor (MVT), ritas i webbläsaren |

Det här är en **testmiljö** och en mall för kommuner som vill göra något liknande. Den är inte en del av pluginet.

## Hur det hänger ihop

```
Rita Detaljplan ──checka in──▶ PostGIS: schemat med planerna (till exempel detaljplaner)
                                       │  vyn publicering.planmosaik (bara antagna och laga kraft)
                                       ▼  rollen karta_ro, bara läsrätt på vyn
                  ┌────────────────────┼────────────────────┐
              GeoServer           QGIS Server             Martin
                  └────────────────────┼────────────────────┘
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
| `docker-compose.yml` | De fyra behållarna: GeoServer, QGIS Server, Martin och nginx. |
| `stil.py` | Planens utseende på ett ställe: mått för gränslinjer och mönster vid olika kartskalor (se "Skala" nedan). |
| `geoserver/` | `konfigurera_geoserver.py` (REST-anrop: lager, lagergrupp och stilar), `bygg_stilar.py` (skriver de skalberoende stilarna ur `stil.py`) och stilarna `plan_*.sld`. |
| `qgis/skapa_qgis_projekt.py` | Skapar QGIS-projektet som QGIS Server publicerar, ritat enligt `stil.py`. |
| `web/nginx.conf` | Vidarebefordran till de tre tjänsterna. GeoServers administration släpps inte ut. |
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

Skalan delas i band och alla tre varianterna räknar likadant (`stil.py`; Origo-stilen i `web/html/planmosaik.js` har
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
| **Vektorrutor** (Martin; GeoServer med tillägget vectortiles) | Små rutor som webbläsaren ritar. Skarpt vid alla zoomnivåer och tar lite av servern. | Stilen måste skrivas om för webbläsaren (här `planmosaik.js`), mönster blir enklare. |

Martin är alltså vektoralternativet i den här miljön. Det är det som skalar bäst när antalet planer växer.

## Det här lärde vi oss

- **Koordinatsystem.** Planerna ligger i SWEREF 99 (här EPSG:3008), men webbkartan går i EPSG:3857 så att OpenStreetMap
  och Martins rutor passar. GeoServer och QGIS Server omprojicerar själva. Martin gör det i SQL. Vill du ha kartan i
  SWEREF 99 kräver Origo `proj4Defs` och ett eget rutnät, och Martins vektorrutor (som är i 3857) går då inte att visa.
- **Hopp vid zoomning (Origo).** Origos exempelkonfiguration har avrundade upplösningar (`9.5546` i stället för
  `9.554628535647…`). Vektorrutor placeras av rutnätet, så felet växer med rutnummer och zoomnivå (flera hundra meter vid
  zoomnivå 17) och planerna flyttar sig när man zoomar. Använd exakta värden: `156543.03392804097 / 2^zoom`.
- **Databasanslutningar.** Martin tar som standard 20 anslutningar, GeoServer upp till 10. Sätt `pool_size` (Martin) och
  `max connections` (GeoServer), och en anslutningsgräns på rollen, annars blir det `too many connections`.
- **Origo och vektorrutor.** Origo 2.10 kan rita vektorrutor men inte fråga dem: en träff på en MVT-yta ger ett fel
  (`getGeometryName is not a function`). Martin-lagret är därför inte frågbart, och klick på planen ger ingen ruta när
  bara Martin är påslaget (GeoServer- och QGIS Server-lagren ger plandata vid klick).
- **Origo.**
  - Det färdiga bygget saknar tillägget `olms` (MapLibre-stilar). Därför har vektorrutorna en egen stil i `planmosaik.js`.
  - `extent` i `index.json` måste vara hela projektionens utbredning. Origo bygger rutnätet av den.
  - Vektorrutor behöver ett eget rutnät med origo uppe till vänster (`tileGrid` på lagret), eftersom Martin levererar
    vanliga XYZ-rutor.
  - npm-paketet `origo` är något helt annat. Hämta från `github.com/origo-map/origo`.
- **QGIS Server.** WMS-lagrets namn är lagrets namn i projektet: kalla lagren som vyerna, annars fungerar inte
  `LAYERS=plan_anvandning`. Behållarens FastCGI-processer ärver inte miljövariabeln `PGSERVICEFILE`. Lägg tjänstefilen på
  `/etc/postgresql-common/pg_service.conf`. Då hamnar lösenordet aldrig i projektfilen.
  QGIS skriver färger som `#AARRGGBB`, inte `#RRGGBBAA`.
- **GeoServer.** Vyer saknar primärnyckel i databasen. Det fungerar, men GeoServer varnar. Etiketterna kan upprepas när
  Origo hämtar kartan i rutor.
- **Minne.** Hela miljön tog ungefär 1 GB (GeoServer 600 MB, QGIS Server 230 MB, Martin 80 MB, nginx 15 MB). Sätt
  minnesgränser (görs i compose-filen) om servern delas med annat.
- **Vektorrutor.** Martin ger geometri och attribut. Texter (planbeteckningar) ritas av webbläsaren. Det gör att de blir
  skarpa, men kräver att kartan har en stil för dem.
