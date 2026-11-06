# Säkerhetsbeskrivning

Det här dokumentet är till för dig som ska bedöma om Rita Detaljplan kan användas i en organisation, till exempel en
kommuns IT-säkerhetsfunktion. Det beskriver vad pluginet gör, vilka data som rör sig vart, vad som är granskat och vad
som inte är det. Rapportera säkerhetsbrister enligt [SECURITY.md](../SECURITY.md).

**Omfattning:** version 0.1.75. Första genomgången gjordes för 0.1.44 (2026-10-02). Den uppdaterades 2026-11-03 för
0.1.75: sökningarna nedan kördes om över hela koden, och filhanteringen i det som tillkommit sedan 0.1.44
(taggningsprogrammet `planbeskrivning/`, arkivpaketet `core/archive.py`) lästes igenom.

**Version 0.1.76 är inte genomgången på nytt.** Den lägger till att taggningsprogrammet kan läsa en JSON-leverans som
plankarta (filen läses med Pythons `json`, tolkas bara som text och tal och ger ett felmeddelande om den är felaktig;
ett test täcker lista högst upp, id som listor och för djup nästling), och ett gränssnitt (`planbeskrivning/pbweb/`) för
webbsidan ritaplan.xyz/tagga.html som pluginet självt inte använder. Webbsidan ingår inte i pluginet och omfattas inte av
det här dokumentet: den kör programmets kod i webbläsaren med Pyodide, som hämtas från cdn.jsdelivr.net (laddarfilen är
låst med en kontrollsumma, de övriga delarna inte), och skickar inga filer vidare.

**Version 0.1.77 är inte heller genomgången på nytt.** Den lägger till en översikt över planerna i en databas (`core/plan_overview.py`), som läser planernas uppgifter med `SELECT`-frågor där scheman och tabeller citeras med samma hjälpfunktioner som resten av lagringen (`quote` och `literal`); schemanamnen kommer ur databasen. Inga nya filer läses eller skrivs och inga nya beroenden tillkommer. Genvägarna (`gui/plan_toolbar.py`) och statusradsspärren (`gui/statusbar_guard.py`) ändrar bara QGIS gränssnitt. Felsökningsskriptet `tools/felsok_omritning.py` ingår inte i zip-filen.

## Läs det här först: vad dokumentet är och inte är

- Pluginet är skrivet med AI-stöd och underhålls av en enskild person på fritiden. Det är en experimentell
  utvecklingsversion.
- Genomgången nedan är en **statisk kodgranskning** (läsning och sökning i källkoden, utförd av underhållaren med AI-stöd).
  Det är **ingen oberoende säkerhetsgranskning** och inget penetrationstest. Sedan 0.1.75 körs dessutom automatisk
  kodanalys (CodeQL och ruff) på GitHub vid varje ändring. De hittar en annan sorts fel än en människa som läser, men
  ersätter inte en oberoende granskning.
- Testsviten (se `tests/`) kontrollerar att funktionerna beter sig rätt och att leveransen följer Lantmäteriets scheman.
  Den bevisar inte att koden är säker.
- En organisation som har krav på säkerhetsgranskning bör låta en oberoende person gå igenom koden. Se
  [Rekommendationer](#rekommendationer-för-en-organisation).

## Kort version för IT-säkerhetsfunktionen

| Fråga | Svar |
| --- | --- |
| Skickas data ut från datorn? | Bara när användaren själv väljer det: hämta Boverkets planbestämmelsekatalog, eller leverera en plan till Lantmäteriet (eller en adress användaren skrivit in). Ingen telemetri, inga analysverktyg, inga uppdateringskontroller i pluginet. |
| Vilka rättigheter behövs? | Inga särskilda. Pluginet körs i QGIS med den inloggade användarens rättigheter. Det installerar inget och ändrar inga systeminställningar. Det startar inga program, förutom att webbläsaren eller filhanteraren öppnas när användaren klickar på en länk (hemsidan, en sparad fil eller mapp). |
| Körs kod som hämtats utifrån? | Nej. Koden använder inte `eval`, `exec`, `subprocess`, `pickle` eller liknande. |
| Vilka beroenden finns? | Bara QGIS (med dess Python, Qt och GDAL). Se materiallistan (SBOM) som följer med varje release. |
| Var lagras lösenord och nycklar? | I QGIS autentiseringsdatabas, aldrig av pluginet. Databaslösenord hanteras av QGIS egna anslutningar. |
| Finns personuppgifter? | Inga i pluginet. Vid utcheckning från PostGIS lagras användarnamn och datornamn i planens metadata (fynd 2). Planbeskrivningens text kan i sig innehålla personuppgifter, men den stannar på användarens dator. |
| Hur kommer pluginet till användaren? | Som zip-fil från GitHub Releases eller via en pluginkälla som pekar på GitHub. Zip-filen byggs reproducerbart, och en kontrollsumma och en materiallista följer med varje release. |
| Är koden granskad? | Av underhållaren med AI-stöd, och automatiskt med CodeQL. **Inte** av en oberoende part. Ingen certifiering finns. |
| Vem svarar vid en sårbarhet? | Underhållaren, via GitHubs privata rapportering (se [SECURITY.md](../SECURITY.md)). Målet är ett första svar inom 14 dagar. Det är en enskild person på fritiden. |

## Sammanfattning

| Område | Bedömning |
| --- | --- |
| Körning av kod från indata (`eval`, `exec`, `subprocess`, `pickle`) | Förekommer inte i pluginets kod |
| Beroenden utanför QGIS och Pythons standardbibliotek | Inga i QGIS. Det fristående taggningsprogrammet kan valfritt köras med PySide6 (se [Beroenden](#beroenden)) |
| Nätverksmål | Tre: Boverket, Lantmäteriet (verifiering/produktion) och en adress som användaren själv anger |
| Hemligheter | Sparas inte av pluginet, utan i QGIS autentiseringsdatabas |
| Databasåtkomst | Via QGIS sparade anslutningar, med användarens egna databasrättigheter |
| Öppna fynd | 4 informativa (fynd 2–5) och 2 nya informativa (fynd 7–8). Två låga fynd är åtgärdade: fynd 1 i 0.1.44 och fynd 6 i 0.1.75 |
| Distribution | Osignerade zip-filer med kontrollsumma och materiallista, och en pluginkälla som pekar på GitHub (se [Leveranskedja](#leveranskedja-och-distribution)) |

## Vad pluginet är och vilka rättigheter det har

Pluginet är ett Python-plugin i QGIS (QGIS 4.0 eller senare). Det körs i QGIS egen process med **samma rättigheter som
den inloggade användaren**. QGIS har ingen sandlåda för plugin, så detta gäller varje QGIS-plugin, oavsett hur det är
skrivet. Pluginet gör inget vid installation utom att QGIS importerar modulen; ingen kod körs från installationsskript.

Omfång: cirka 21 000 rader Python under `rita_detaljplan/` (utan tester), varav ungefär en femtedel är taggningen av
planbeskrivningen (`planbeskrivning/`) som också kan köras som ett fristående program utanför QGIS.

## Dataflöden

| Vad | Varifrån | Vart | Hur |
| --- | --- | --- | --- |
| Planbestämmelsekatalogen | Boverkets öppna API (`api.boverket.se`) | Cache i användarens QGIS-profil | Bara när användaren väljer *Uppdatera planbestämmelsekatalogen*. Via QGIS nätverksstack |
| Planleverans (JSON) | Lokal plan | Lantmäteriets API (`api-ver.` eller `api.lantmateriet.se`), eller en adress användaren anger | Bara när användaren väljer *Leverera*. Via QGIS nätverksstack, https |
| Planleverans (fil) | Lokal plan | En JSON-fil som användaren pekar ut | Skrivs av användaren själv |
| Importerad leverans | JSON-fil som användaren väljer | Ny lokal plan | Läses som JSON, tolkas av `core/import_ngp.py` |
| Plandata | Lokal GeoPackage eller PostGIS-schema | QGIS lager | GDAL/SQLite respektive QGIS PostgreSQL-leverantör |
| Taggning av planbeskrivningen | Word-fil, plankarta (`.qgz`) och GeoPackage som användaren väljer | Ny Word-fil som användaren sparar (originalet ändras inte) | Läses lokalt med Pythons `zipfile`, `xml.etree` och `sqlite3` (skrivskyddat). Inget nätverk. Se fynd 6 och 7 |
| Arkivpaket | Filer som användaren väljer | En ny mapp med kopior, PREMIS-metadata och scheman | Skrivs lokalt av `core/archive.py`. Originalen rörs inte. Kontroll av ett paket (`verify_package`) räknar bara om kontrollsummor och läser inte utanför paketmappen |

Nätverksanrop finns bara i `core/ngp_client.py` och `core/catalog_store.py`. Pythons `urllib` används enbart för att tolka
och kontrollera adresser (`urllib.parse`), inte för att hämta något. Pluginet skickar ingen telemetri, och det finns
inga andra nätverksmål i koden.

## Hemligheter och inloggning

- **Lantmäteriets nyckel och hemlighet** sparas inte av pluginet. Användaren väljer en autentiseringskonfiguration i QGIS
  autentiseringsdatabas (typen *Grundläggande autentisering*). Pluginet sparar bara konfigurationens id i QGIS
  inställningar (`QgsSettings`), tillsammans med miljö och adresser.
- **Åtkomsttoken** hämtas med `client_credentials`, hålls bara i minnet i klientobjektet och sparas inte på disk.
  Den förnyas vid 401.
- **Databaslösenord** hanteras av QGIS egna PostgreSQL-anslutningar. Pluginet frågar aldrig efter lösenord och väljer en
  befintlig anslutning ur QGIS lista.
- **Projektfiler (.qgz)** får av pluginet anslutningens *namn*, schema, plan-id, ett utcheckningslås (slumpmässig
  token) och, efter en leverans, mottagningens och planens id hos Lantmäteriet samt miljöns namn. Pluginet lägger inga
  lösenord eller nycklar i projektet. Hur en PostgreSQL-lagerkälla lagrar inloggning i projektfilen styrs av QGIS, inte
  av pluginet: använd en autentiseringskonfiguration. Leveransinställningarna (adresser, vald autentisering) ligger i
  användarens profil, inte i projektet, så en delad projektfil kan inte styra om inloggningsuppgifterna till en annan
  adress. Se fynd 5.
- Adresser till API:et och tokentjänsten måste börja med `https://`. Bara `http://` mot `localhost` och `127.0.0.1`
  tillåts (för tester). Omdirigeringar följs inte vid leverans.
- QGIS egna inställningar för proxy och certifikat gäller, så TLS-kontrollen är QGIS standard. Pluginet stänger aldrig av
  certifikatkontroll och använder inte certifikatfästning.

## Filer

Pluginet skriver:

- planens GeoPackage och projektfil (`.qgz`) i den mapp användaren väljer,
- en lokal arbetskopia (GeoPackage) vid utcheckning från PostGIS,
- katalogcachen `planbestammelsekatalog.json` i QGIS-profilen (skrivs först till en `.tmp`-fil och byter sedan namn),
- leveransfilen som användaren själv väljer att spara,
- en taggad Word-fil, en CSV-översikt och en utbytesfil från taggningsprogrammet, på den plats användaren väljer
  (originalfilen skrivs inte över),
- arkivpaket (en ny mapp med kopior och metadata) under en mapp användaren väljer,
- inställningar via `QgsSettings` (det fristående taggningsprogrammet använder Qts `QSettings` under namnet *Planbeskrivning*).

Pluginet raderar filer i två situationer: den lokala arbetskopian när en plan checkas in eller utcheckningen hävs
(`core/checkout.py`), och en halvfärdig arkivpaketmapp som pluginet självt just skapade när bygget av paketet
misslyckades (`core/archive.py`). Det raderar aldrig filer som användaren valt.

## Databaser

**GeoPackage** nås med Pythons `sqlite3` och GDAL. Värden skickas som bundna parametrar. Tabellnamn kommer från pluginets
egen modell, inte från indata.

**PostGIS** nås med QGIS anslutningsobjekt (`executeSql`). SQL byggs som text, eftersom gränssnittet inte har bundna
parametrar. Skydden är:

- identifierare (schema, plan-id) valideras mot `^[a-z][a-z0-9_]{0,62}$` och citeras med dubbla citattecken
  (`quote()`), och schemat får inte vara `public`, `information_schema` eller börja med `pg_`,
- textvärden skrivs som SQL-literaler med fördubblade enkla citattecken (`literal()`),
- tal skrivs via `int()` och `float()`,
- ett dollarcitat i incheckningsblocket väljs så att det inte förekommer i innehållet.

Det här är korrekt förutsatt att databasen har `standard_conforming_strings = on` (förvalt sedan PostgreSQL 9.1). Se fynd 3.

Pluginet kör `DROP SCHEMA ... CASCADE` bara för att städa bort ett schema som just skapades i samma anrop och där
skapandet misslyckades halvvägs. Det rör aldrig ett schema som fanns innan.

**Behörighet:** pluginet har ingen egen åtkomstkontroll. Vem som kan läsa och ändra planer avgörs helt av
databasrollen i QGIS-anslutningen. Utcheckningens lås (se fynd 2) är en samarbetsmekanism för att undvika samtidig
redigering, inte en säkerhetsfunktion.

## Beroenden

Pluginet importerar bara QGIS (`qgis`, `osgeo`/GDAL) och Pythons standardbibliotek (bland annat `json`, `re`, `sqlite3`,
`uuid`, `getpass`, `platform`, `zipfile`, `xml.etree`, `urllib.parse`). Det installerar inga paket med `pip` och har
ingen `requirements`-fil. Uppdateringar av beroenden följer därför QGIS egna.

Ett enda annat paket nämns i koden: **PySide6**, och bara för det fristående taggningsprogrammet
(`python -m rita_detaljplan.planbeskrivning`, se `planbeskrivning/pbapp/qt/`). I QGIS används PyQt6 från QGIS och PySide6
behövs inte. Den som kör programmet fristående installerar PySide6 själv och ansvarar för dess uppdateringar.

En medföljande kopia av planbestämmelsekatalogen, kommunlistan, Lantmäteriets JSON-scheman, PREMIS-schemat och
stilbiblioteket ligger som filer i `rita_detaljplan/data/` (se [NOTICE.md](../NOTICE.md)).

**Materiallista (SBOM).** `tools/build_sbom.py` skapar en materiallista i CycloneDX-format
(`rita_detaljplan-<version>.sbom.cdx.json`) med pluginet, de medföljande datafilerna (med kontrollsummor) och det som
krävs men inte levereras (QGIS med Python, PyQt och GDAL). Skriptet läser alla importer i koden och avbryter om ett nytt
paket dyker upp som inte är listat, så listan kan inte tyst bli ofullständig. Den följer med varje release.

Testerna kräver bara QGIS och Pythons `unittest`.

## Leveranskedja och distribution

- Koden ligger öppet på GitHub under GPL-2.0-eller-senare. Commits och taggar är **inte signerade**.
- Release-filen (`rita_detaljplan-<version>.zip`) byggs reproducerbart av `tools/build_zip.py` (samma innehåll ger samma
  zip). Från och med 0.1.75 följer en **SHA-256-kontrollsumma** (`.zip.sha256`) och en **materiallista** (`.sbom.cdx.json`)
  med varje release. Zip-filen är **inte signerad**. Du kan själv kontrollera den: kontrollera taggen i repot, kör
  `python tools/build_zip.py` och jämför kontrollsumman med den som publicerats.
- Det finns automatiska kontroller på GitHub (`.github/workflows/`): CodeQL (statisk kodanalys, vid varje ändring och en
  gång i veckan), ruff (kodkontroll), en kontroll att zip-filen blir identisk vid två byggen och att koden inte fått nya
  beroenden, samt OpenSSF Scorecard. Dependabot håller de fastlåsta versionerna av dessa verktyg uppdaterade. Testsviten
  (`tests/`) kräver QGIS 4 och körs inte på GitHub utan lokalt före varje release.
- Pluginkällan (`plugins.xml`) läses från `main` på GitHub. Den som kan skriva till repot kan alltså få kod installerad hos
  alla som uppdaterar via pluginkällan. Skyddet är kontot på GitHub. Läget 2026-11-03 (kontrollerat via GitHubs API): en regel för `main` stoppar radering och tvångspush, GitHubs
  hemlighetsskanning och Dependabot-varningar är på, privat rapportering av sårbarheter är på och organisationen kräver
  tvåfaktorsinloggning. Regeln kräver varken pull request eller gröna kontroller, eftersom underhållaren pushar direkt till
  `main`. Push-skyddet, som stoppar en push som innehåller en hemlighet, är påslaget (2026-11-03). Samma inställningar gäller
  organisationens övriga repon, bland annat integrationen för Origo, [rita-detaljplan-origomap](https://github.com/ritaplan/rita-detaljplan-origomap).
- Pluginet är **inte** publicerat i QGIS officiella pluginarkiv och har därför inte genomgått dess granskning.

## Fynd

Allvarlighetsgrad: *låg* = kan missbrukas men med liten effekt, *information* = bra att känna till, ingen åtgärd krävs.

### 1. Ofiltrerad text i dialogrutornas rika text (låg, åtgärdad i 0.1.44)

Text från Boverkets katalog (`bestammelse_dialog.py`), planens namn och API-adressen (`delivery_dialog.py`,
`ngp_dialog.py`) och kontrollistans rader (`plan_info_dialog.py`) sätts in i dialogrutor som tolkar Qts rika text
(`setHtml`, `RichText`) utan att specialtecken först kodas.

*Effekt:* En manipulerad katalogpost (om Boverkets API eller anslutningen dit skulle vara komprometterad) eller ett
planamn med HTML kan ändra hur texten i en dialogruta ser ut, till exempel dölja eller förvränga bekräftelsetexten vid
leverans. Qts rika text kör inga skript och hämtar inga fjärrresurser, så ingen kod kan köras den vägen.
*Åtgärd:* texten kodas nu med `html.escape` (`gui/richtext.py`) innan den läggs in i dessa dialogrutor, och det finns
tester för det. Qt:s `QLabel` tolkar som standard även text som ser ut som HTML (automatiskt textformat). Alla
andra textfält har inte gåtts igenom ett och ett, så det kan finnas fler ställen med samma beteende och samma låga effekt.

### 2. Låset avslöjar användarnamn och datornamn (information)

Vid utcheckning från PostGIS skrivs operativsystemets användarnamn och datorns namn (`getpass.getuser()`,
`platform.node()`) i planens metadatatabell, så att andra kan se vem som har planen. Det syns för alla som kan läsa
schemat. Räkna det som personuppgift i er bedömning.

### 3. SQL byggs som text (information)

Se avsnittet [Databaser](#databaser). Skyddet bygger på validerade identifierare och korrekt citering. Det finns
enhetstester för `quote()` och `literal()`, men inget test med avsiktligt illasinnade indata mot en riktig databas. Mönstret är mer sårbart för framtida ändringar än bundna parametrar skulle vara.

### 4. Egen API-adress (information)

I inställningarna kan användaren välja *Egen adress* i stället för Lantmäteriets miljöer. Nyckel och hemlighet från den
valda autentiseringskonfigurationen skickas då till den tokentjänst som användaren själv har skrivit in. Det är avsiktligt
(för test och andra miljöer) men innebär att en vilseledd användare kan skicka sina uppgifter till fel adress. Adressen
måste vara `https://`.

### 5. Leveransmottagning lagras i projektfilen (information)

Efter en leverans sparas mottagningens id, planens id och miljöns namn i projektfilen, så att nästa leverans uppdaterar
samma mottagning. En manipulerad projektfil skulle kunna peka en senare leverans mot ett annat mottagnings-id. Om det
lyckas avgörs av Lantmäteriets behörighetskontroll mot användarens nyckel; det har inte testats här. Öppna därför inte
projektfiler från okända källor och leverera, som alltid, först till verifieringsmiljön.

### 6. Påhittat antal punkter i en geometri kunde frysa taggningsprogrammet (låg, åtgärdad i 0.1.75)

Taggningsprogrammet läser plankartans ytor direkt ur GeoPackage-filen med egen kod (`planbeskrivning/pbkarna/geometri.py`)
för att rita en enkel karta. En geometri som i sitt huvud påstod sig ha upp till fyra miljarder punkter, men saknade data,
fick läsaren att bygga en läsmall i flera gigabyte innan den upptäckte att filen var för kort. En geometrisamling i en
samling i en samling (tusentals nivåer) kunde på samma sätt gå över Pythons rekursionsgräns.

*Effekt:* Den som öppnar en manipulerad GeoPackage i taggningsprogrammet kan få programmet att frysa eller ta slut på
minne. Ingen kod körs och inga data läcker; det är en driftstörning på den egna datorn och kräver att användaren själv
öppnar filen. Provat: den gamla koden hängde i över två minuter på ett sådant indata.
*Åtgärd:* antalet punkter kontrolleras mot hur mycket data som finns innan något byggs, och samlingar får högst åtta
nivåer. Felaktig geometri hoppas över, som tidigare. Det finns ett test med båda fallen.

### 7. Filer läses utan storleksgräns (information)

Taggningsprogrammet och arkivpaketet läser filer som användaren själv valt: Word-filer och projektfiler (zip-filer) läses
helt till minnet (`planbeskrivning_docx.py`, `plankarta.py`, `archive.py`) och deras XML tolkas med Pythons
`xml.etree.ElementTree`. En avsiktligt konstruerad fil (en zip-bomb eller en mycket stor XML-del) kan därför ta mycket
minne och tid. `ElementTree` hämtar inga externa entiteter eller dokumenttyper, så filer kan inte få programmet att läsa andra filer eller
anropa nätverket. Skyddet mot "entitetsexplosioner" ligger i XML-biblioteket expat (version 2.4 och senare har gränser);
vilken version som följer med din QGIS har inte kontrollerats här. Ingenting skrivs ut ur en zip-fil till disk (inga `extractall`), så
sökvägsangrepp via filnamn i zip-filen är inte möjliga.
*Rekommendation:* öppna inte Word-filer, projekt eller GeoPackage från okända avsändare. Ingen åtgärd planeras.

### 8. Fristående program med eget beroende (information)

Det fristående taggningsprogrammet kräver PySide6 (se [Beroenden](#beroenden)). Det är ingen del av pluginet i QGIS,
men finns i samma paket och körs bara om någon startar `python -m rita_detaljplan.planbeskrivning`. PySide6 installeras
då av användaren och hålls uppdaterat av den som installerade det. Ett eventuellt skydd mot sårbarheter i PySide6 ligger
utanför det här dokumentet.

## Det som inte omfattas

- Ingen dynamisk analys, ingen fuzzning och inget penetrationstest. (Fynd 6 hittades genom att läsa koden och bekräftades
  med ett enda handgjort indata; en riktig fuzzning av filläsarna skulle troligen hitta mer.)
- Ingen skanning av beroenden i verktyg: det finns inga externa Python-beroenden i QGIS att skanna, men QGIS, GDAL och
  PostgreSQL ligger utanför pluginets kontroll. Materiallistan gör att en organisation kan göra den kontrollen själv.
- QGIS och GDAL:s egna sårbarheter, till exempel vid inläsning av hotfyllda filer, bedöms inte här.
- Dataskydd (GDPR) bedöms inte, förutom att fynd 2 pekar på att användarnamn kan lagras.
- Tillgänglighet, drift och support.
- Webbsidan ritaplan.xyz/tagga.html (se Omfattning ovan): den är en egen leverans med egna beroenden (Pyodide från ett
  publikt nätverk) och är inte granskad här.

## Rekommendationer för en organisation

1. **Låt en oberoende person granska koden** innan produktionsanvändning. Börja med `core/ngp_client.py`,
   `core/storage.py`, `core/checkout.py`, `core/catalog_store.py` och `core/settings.py`. Det är där nätverk,
   inloggning och databas finns. Fortsätt med filläsarna (`planbeskrivning/pbkarna/`, `core/archive.py`), som tolkar filer
   från andra (fynd 6 och 7).
2. **Installera en fast, granskad version** centralt (zip-filen), och använd inte den öppna pluginkällan i
   produktionsmiljön. Jämför filens innehåll med taggen i repot innan den godkänns.
3. **Börja i Lantmäteriets verifieringsmiljö** (`api-ver`), inte i produktion, och kontrollera leveransen där först.
4. **Begränsa databasrollen** som används i PostGIS-anslutningen till det schema och de tabeller som behövs, eftersom
   pluginet inte har någon egen behörighetskontroll.
5. **Bestäm vem som äger underhållet.** En enskild frivillig underhållare är en verksamhetsrisk. Ett kommunalt samarbete
   eller en organisation som tar över repot minskar den.
6. **Skydda GitHub-kontot** med tvåfaktorsinloggning om ni använder repot som källa, och överväg en egen kopia (fork)
   som ni själva kontrollerar.
7. **Läs in materiallistan** (`.sbom.cdx.json`) i ert eget verktyg för sårbarhetsbevakning, så att QGIS-versionen som
   pluginet körs i följs upp tillsammans med övriga program.

## Så kan du verifiera uppgifterna

Kontrollera att en nedladdad zip-fil är den som publicerats (från och med 0.1.75, i PowerShell):

```
Get-FileHash rita_detaljplan-<version>.zip -Algorithm SHA256
```

Värdet ska vara detsamma som i filen `rita_detaljplan-<version>.zip.sha256` på releasesidan. Vill du inte lita på att filen
är oförändrad sedan den laddades upp, hämta taggen `v<version>` från repot, kör `python tools/build_zip.py` och jämför
kontrollsumman: bygget är reproducerbart, så samma källkod ger exakt samma zip-fil.

Sökningar mot källkoden (kör i repots rot):

```
# Inga dynamiska kodkörningar eller processer (träffar i dialogrutor är Qts egna .exec())
grep -rnE "\b(eval|exec|compile|__import__|subprocess|os\.system|pickle|marshal)\b" rita_detaljplan --include=*.py

# Alla nätverksanrop
grep -rnE "QNetwork|QgsNetworkAccessManager|QgsBlockingNetworkRequest|urlopen|socket" rita_detaljplan --include=*.py

# Alla importer som inte är QGIS eller standardbibliotek
grep -rhE "^\s*(import|from) " rita_detaljplan --include=*.py
```
