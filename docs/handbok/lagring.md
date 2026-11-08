# Lagring, databaser och flera planer

En plan kan lagras som en **lokal GeoPackage-fil** (standard) eller i en **PostGIS-databas**. Du kan också ha flera
planer laddade samtidigt.

## GeoPackage eller PostGIS?

| | GeoPackage | PostGIS |
|---|---|---|
| Passar för | En person, eller planer som delas som filer. | Flera som arbetar mot samma databas. |
| Kräver | Ingenting. | En PostgreSQL-databas med PostGIS och en sparad anslutning i QGIS. |
| Redigering | Direkt i filen. | Checka ut, redigera lokalt, checka in. |

> **PostGIS-stödet** är testat mot en låtsasdatabas och prövat mot en riktig PostGIS-databas, men inte i alla miljöer.
> Prova först på en testplan och säkerhetskopiera schemat innan du checkar in en viktig plan.

## Skapa en plan i PostGIS

1. Välj **Ny detaljplan…** och välj **PostGIS-databas** under *Lagras i*.
2. Välj en av QGIS sparade **anslutningar**.
3. Ange ett **schema**. Finns det redan används det, annars skapas det.
4. Ange ett **plan-id**, planens identifierare i schemat. Ett förslag hämtas från plannamnet.

Flera planer kan dela samma schema. De ligger då i samma tabeller och måste ha samma koordinatsystem. Behöver du flera
SWEREF 99-zoner använder du olika scheman för dem.

Projektfilen (`.qgz`) sparas i en mapp och pekar på databasen.

## Öppna en plan

Klicka på **Öppna** i verktygsfältet. Finns det databasanslutningar får du välja fil eller databas.

För en databas visas en **översikt över alla planer** i databasen (alla scheman som skapats med pluginet) med en rad per
plan och kolumner för beteckning, namn, syfte, planstatus, plantyp, diarienummer, påbörjad, antagande, laga kraft,
genomförandetid och vem som har planen utcheckad. Listan är sorterad på planbeteckning, där tal räknas som tal (1, 2, 3,
10 och 1002 i den ordningen). Klicka på en kolumnrubrik för att sortera på något annat.

- **Filtrera** genom att skriva i rutan (delar av namn, beteckning, syfte, diarienummer …, flera ord kan kombineras) och
  med listorna för schema (bredvid databasvalet), planstatus, plantyp och utcheckning (*Bara lediga* / *Bara
  utcheckade*). Under listan står hur många planer som syns av alla och hur många som är valda.
- **Välj flera planer** med Ctrl eller Skift och öppna dem på en gång. De läggs till bredvid varandra, och den sist
  laddade planen blir den aktiva.
- **Checka ut och öppna** låser planen och skapar en lokal kopia som du redigerar. Har du valt flera hämtas och låses de
  en i taget. Knappen är grå om någon av dem har checkats ut av någon annan.
- **Öppna skrivskyddad** visar planerna direkt från databasen utan att låsa dem. Det är också vad dubbelklick gör. Du kan
  checka ut en plan senare med knappen **Checka ut** i verktygsfältet.

**Rita Detaljplan → Öppna detaljplan (GeoPackage)…** öppnar en plan-fil direkt.

> Lägg inte till planens PostGIS-lager med QGIS egen lagerdialog. Använd pluginets **Öppna**, annars visas alla planers
> rader i schemat blandade och pluginets verktyg känner inte igen lagret.

## Checka ut och checka in

Att rita direkt mot en databas över nätet blir långsamt. En plan som öppnas från en databas är därför skrivskyddad
tills du checkar ut den.

<!-- FILM: checka-ut-in | Checka ut en plan från PostGIS, redigera och checka in, ca 2 min -->

### Checka ut

Knappen **Checka ut** (databasikonen med pil nedåt) syns alltid i verktygsfältet men är grå när planen bara ligger i en
lokal fil. Du kan också välja **Checka ut och öppna** direkt när du öppnar planen från databasen. Klicka på knappen eller
på pennan. Pluginet

1. låser planen i databasen,
2. kopierar den till en lokal GeoPackage som du redigerar i full fart.

### Checka in

Klicka på **Checka in** (samma knapp, nu med pil uppåt). Pluginet

1. skriver tillbaka hela planen i en enda transaktion,
2. släpper låset,
3. pekar lagren mot databasen igen,
4. tar bort den lokala kopian.

Här kan du också **kasta utcheckningen**. Låset släpps då utan att något sparas.

### Om någon annan har planen utcheckad

Bara en person åt gången kan ha planen utcheckad. Försöker du checka ut en låst plan ser du vem som har den och sedan
när. Är utcheckningen övergiven kan du **bryta låset**. Den andras ändringar som inte checkats in går då inte längre
att checka in.

### Om QGIS kraschar

Den lokala kopian finns kvar i QGIS profilmapp under `detaljplan_ngp/checkouts`. Den erbjuds nästa gång du checkar ut
planen.

## Skicka planen som fil

Det säkraste sättet att ge planen till någon annan är en **leverans** (*Spara som JSON-fil*) eller ett **arkivpaket**.
Arkivpaketet innehåller en ögonblicksbild av planens GeoPackage som alltid är hel.

Vill du i stället kopiera själva `.gpkg`-filen gäller detta:

- **Spara först.** Ändringar du inte sparat finns bara i QGIS minne och följer inte med. Avsluta redigeringen eller klicka
  på *Spara lagerredigeringar*.
- **Stäng helst projektet i QGIS** innan du kopierar. Medan planen är öppen håller QGIS GeoPackage i ett läge där de
  senaste ändringarna kan ligga i en hjälpfil, `<namn>.gpkg-wal`, bredvid planfilen. En kopia av bara `.gpkg`-filen kan
  då sakna dem och se tom ut.
- Pluginet skriver in ändringarna i `.gpkg`-filen varje gång du har sparat, så en kopia ska bli hel även medan planen
  är öppen. Hittar du ändå en `-wal`-fil bredvid planen: spara en gång till, eller ta med både `.gpkg`- och
  `-wal`-filen.

## Flera planer samtidigt

Du kan ha flera planer laddade i samma projekt. **Öppna**, **Ny detaljplan** och **Importera leverans** lägger till
planen bredvid de andra. Bara en plan är **aktiv** åt gången, och pluginets verktyg arbetar bara mot den.

- Den plan du senast skapade eller öppnade blir aktiv.
- Den aktiva planen visas i QGIS fönstertitel och i statusraden när fler än en plan är laddad.
- Pennan frågar vilken plan du vill redigera.
- **Rita Detaljplan → Byt aktiv plan…** byter aktiv plan utan att börja redigera.
- Dialogerna *Planens uppgifter*, *Topologikontroll*, *Kontrollera planen* och *Leverans och export* har en rad
  **Aktiv plan** där du kan byta plan direkt.
- **Rita Detaljplan → Stäng aktiv plan** tar bort den aktiva planens lager ur projektet. Filen eller databasen rörs
  inte.

## Mer

Hur lagringen och utcheckningen fungerar tekniskt beskrivs i [Under huven](teknik.md).
