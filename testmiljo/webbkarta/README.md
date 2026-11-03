# Planmosaik i en webbkarta: testmiljö

Visar alla antagna detaljplaner och planer med laga kraft sida vid sida i en webbkarta (Origo), med data direkt ur
plandatabasen i PostGIS. Samma data publiceras på tre sätt, så att de kan jämföras:

| Lager i kartan | Tjänst | Protokoll |
|---|---|---|
| GeoServer (WMS) | GeoServer 3.0 | WMS och WFS |
| QGIS Server (WMS) | QGIS Server 4.2 | WMS och WFS |
| Martin (vektorrutor) | Martin 1.14 | vektorrutor (MVT) |

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

- **Pluginets tabeller rörs aldrig.** Tjänsterna läser en vy i ett eget schema, `publicering`. Vyn bestämmer vilka planer
  som är offentliga (här: *antagen* och *laga kraft*) och vilka uppgifter som visas.
- **Läsrollen `karta_ro`** kommer bara åt schemat `publicering`. Den kan inte skriva och inte läsa planernas egna tabeller.
- Kartan visar en plan så fort den har checkats in i databasen. Det behövs ingen export.

## Filerna

| Fil | Vad den gör |
|---|---|
| `skapa_testschema.py` | Gör SQL för ett testschema med fem demoplaner (olika status) från en GeoPackage. Behövs bara om du saknar planer i databasen. |
| `publicering.sql` | Vyn `publicering.planmosaik`. **Byt schemanamnet** (`detaljplaner_test`) mot ert plan-schema. |
| `publicering_roll.sh` | Skapar läsrollen `karta_ro` med slumpat lösenord i `.env`. |
| `forbered.sh` | Slumpar GeoServers adminlösenord och skriver `qgis/pg_service.conf` ur `.env`. |
| `docker-compose.yml` | De fyra behållarna: GeoServer, QGIS Server, Martin och nginx. |
| `geoserver/` | `konfigurera_geoserver.py` (REST-anrop) och stilen `planmosaik.sld`. |
| `qgis/skapa_qgis_projekt.py` | Skapar QGIS-projektet som QGIS Server publicerar (stil, WMS och WFS påslaget). |
| `web/nginx.conf` | Vidarebefordran till de tre tjänsterna. GeoServers administration släpps inte ut. |
| `web/html/` | Origo-kartan: `index.json` (innehållet), `planmosaik.js` (stilen för vektorrutorna), `index.html`. |
| `hamta_origo.sh` | Hämtar Origos färdiga filer (`js/`, `css/`, `img/`) från GitHub. |
| `nginx-host/` | Lägger till och tar bort `/planmosaik/` i värdens nginx (kräver sudo). |

## Sätta upp

Kräver Docker med Compose och en PostGIS-databas som tjänsterna når över ett Docker-nätverk. I compose-filen heter
nätverket `postgis_default` och databasen `postgis`. Ändra dem om er miljö ser annorlunda ut. Databasen måste släppa in
anslutningar från behållarna, och här kräver den SSL (`sslmode=require` är satt överallt).

1. **Databasen.** Kör `publicering.sql` som databasens ägare, sedan `sh publicering_roll.sh`.
2. **Hemligheter och filer.** `sh forbered.sh`
3. **Origo.** `sh hamta_origo.sh`. Skriver inte över `index.html`, `index.json` eller `planmosaik.js`.
4. **QGIS-projektet.** Kommandot står överst i `qgis/skapa_qgis_projekt.py`.
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

## Det här lärde vi oss

- **Koordinatsystem.** Planerna ligger i SWEREF 99 (här EPSG:3008), men webbkartan går i EPSG:3857 så att OpenStreetMap
  och Martins rutor passar. GeoServer och QGIS Server omprojicerar själva. Martin gör det i SQL. Vill du ha kartan i
  SWEREF 99 kräver Origo `proj4Defs` och ett eget rutnät, och Martins vektorrutor (som är i 3857) går då inte att visa.
- **Origo.**
  - Det färdiga bygget saknar tillägget `olms` (MapLibre-stilar). Därför har vektorrutorna en egen stil i `planmosaik.js`.
  - `extent` i `index.json` måste vara hela projektionens utbredning. Origo bygger rutnätet av den.
  - Vektorrutor behöver ett eget rutnät med origo uppe till vänster (`tileGrid` på lagret), eftersom Martin levererar
    vanliga XYZ-rutor.
  - npm-paketet `origo` är något helt annat. Hämta från `github.com/origo-map/origo`.
- **QGIS Server.** Behållarens FastCGI-processer ärver inte miljövariabeln `PGSERVICEFILE`. Lägg tjänstefilen på
  `/etc/postgresql-common/pg_service.conf`. Då hamnar lösenordet aldrig i projektfilen.
  QGIS skriver färger som `#AARRGGBB`, inte `#RRGGBBAA`.
- **GeoServer.** Vyer saknar primärnyckel i databasen. Det fungerar, men GeoServer varnar. Etiketterna kan upprepas när
  Origo hämtar kartan i rutor.
- **Minne.** Hela miljön tog ungefär 1 GB (GeoServer 600 MB, QGIS Server 230 MB, Martin 80 MB, nginx 15 MB). Sätt
  minnesgränser (görs i compose-filen) om servern delas med annat.
- **Vektorrutor.** Martin ger geometri och attribut. Texter (planbeteckningar) ritas av webbläsaren. Det gör att de blir
  skarpa, men kräver att kartan har en stil för dem.
