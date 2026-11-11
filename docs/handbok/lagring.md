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
3. Ange ett **schema**. Finns det redan används det, annars skapas det. Har du bara rätt i ett eget schema (vanligt i
   kommuner), ange det schemat: du behöver inte få skapa nya scheman.
4. Ange ett **plan-id**, planens identifierare i schemat. Ett förslag hämtas från plannamnet.

Flera planer kan dela samma schema. De ligger då i samma tabeller och måste ha samma koordinatsystem. Behöver du flera
SWEREF 99-zoner använder du olika scheman för dem.

Projektfilen (`.qgz`) sparas i en mapp och pekar på databasen.

## Öppna en plan

Klicka på **Öppna** i verktygsfältet. Finns det databasanslutningar får du välja fil eller databas.

För en databas öppnas **databashanteraren**. Den nås också direkt med databasknappen *Databashanteraren* i verktygsfältet
och med **Rita Detaljplan → Databashanteraren…**. Där finns en **översikt över alla planer** i databasen (alla scheman som skapats med pluginet) med en rad per
plan och kolumner för beteckning, namn, syfte, planstatus, plantyp, diarienummer, påbörjad, antagande, laga kraft,
genomförandetid, skrivskydd och vem som har planen utcheckad. Listan är sorterad på planbeteckning, där tal räknas som tal (1, 2, 3,
10 och 1002 i den ordningen). Klicka på en kolumnrubrik för att sortera på något annat.

- **Filtrera** genom att skriva i rutan (delar av namn, beteckning, syfte, diarienummer …, flera ord kan kombineras) och
  med listorna för schema (bredvid databasvalet), planstatus, plantyp, utcheckning (*Bara lediga* / *Bara
  utcheckade*) och skrivskydd (*Bara skrivskyddade* / *Bara redigerbara*). Under listan står hur många planer som syns av alla och hur många som är valda.
- **Välj flera planer** med Ctrl eller Skift och öppna dem på en gång. De läggs till bredvid varandra, och den sist
  laddade planen blir den aktiva.
- **Checka ut och öppna** låser planen och skapar en lokal kopia som du redigerar. Har du valt flera hämtas och låses de
  en i taget. Knappen är grå om någon av dem har checkats ut av någon annan.
- **Öppna skrivskyddad** visar planerna direkt från databasen utan att låsa dem. Det är också vad dubbelklick gör. Du kan
  checka ut en plan senare med knappen **Checka ut** i verktygsfältet.
- En **skrivskyddad** plan (se *Skrivskydda planer som inte får ändras* nedan) kan bara öppnas skrivskyddad. Knappen
  *Checka ut och öppna* är grå så länge någon av de valda planerna är skyddad.

**Rita Detaljplan → Öppna detaljplan (GeoPackage)…** öppnar en plan-fil direkt.

> Lägg inte till planens PostGIS-lager med QGIS egen lagerdialog. Använd pluginets **Öppna**, annars visas alla planers
> rader i schemat blandade och pluginets verktyg känner inte igen lagret.

## Planmosaik: alla planer i ett schema på en gång

Vill du se alla planer i ett schema tillsammans, som en enda karta, klickar du på **Planmosaik…** i dialogen för att
öppna en plan ur databasen (*Öppna → PostGIS-databas…*). Då läser QGIS databasens tabeller direkt, utan att ladda varje
plan för sig.

1. Kontrollera **databas** och **schema**. Det du valt i översikten följer med.
2. Välj vilka planer som ska med efter **planstatus**. Rutorna visar hur många planer det finns med varje status.
   Förvalt är de som gäller: *antagen* och *laga kraft*. Äldre, ersatta och upphävda planer ligger ofta över nyare, så
   ta bara med dem om du vill se dem.
3. Klicka på **Öppna planmosaik**. Kartan zoomar till planerna.

Mosaiken är en grupp i lagerpanelen med planområden, användning och egenskaper, med samma färger och mönster som i en
plan. Några saker att veta:

- **Den är skrivskyddad.** Du kan inte rita eller ändra i den, och pluginets verktyg räknar den inte som en plan. Vill du
  redigera en plan öppnar du den med **Öppna** som vanligt. Den kan ligga i projektet bredvid mosaiken.
- **Detaljerna visas först när du zoomat in.** Användningsytor ritas från skalan 1:200 000, och egenskapsytor
  och egenskapslinjer från 1:2 000, annars blir kartan långsam med många planer. Egenskapspunkter visas inte i mosaiken
  (de ritar bara en text intill punkten). Planområdena syns alltid. Gränserna kan ändras i
  lagrens egenskaper (*Återgivning*).
- **Ett schema i taget.** Varje schema har sitt eget koordinatsystem. Öppna mosaiken igen för samma schema med andra
  statusar så ersätts den förra. Mosaiker för olika scheman kan ligga bredvid varandra.
- **Klicka på en yta med QGIS Identifiera** för att se vilken plan den hör till.
- Har schemat skapats med en äldre version av pluginet får du veta det. Öppna en plan i schemat först, så uppgraderas det.

## Importera och exportera planer

Under listan har databashanteraren knappar för att hantera planerna: **Importera plan…**, **Exportera valda**,
**Kopiera plan…**, **Ta bort plan…**, **Skrivskydda…**, **Bryt skrivskydd…** och **Bryt lås…**. Importen och exporten flyttar planer mellan databasen och filer,
åt båda hållen, som **GeoPackage** (hela planen som den är)
eller som **leverans i JSON-format** (Lantmäteriets format, samma som *Leverans och export* skriver).

### Importera en plan till databasen

Du har en plan som en GeoPackage-fil, till exempel från innan ni började använda en databas, eller en leverans (`.json`)
från ett annat verktyg, och vill lägga in den.

1. Klicka på **Importera plan…** i databashanteraren.
2. Välj **planfilen**: en `.gpkg` som Rita Detaljplan har skapat, eller en leverans i JSON-format.
3. Välj **databas** och **schema**. Finns schemat redan måste det ha planens koordinatsystem. Skriv ett nytt schemanamn
   för att skapa ett.
4. Kontrollera **plan-id**. Det föreslås från filnamnet och måste vara unikt i schemat.
5. För en **leverans** anger du också **kommun** och **koordinatsystem**, eftersom de inte följer med filen (kommunen
   föreslås från filen).
6. Klicka på **Importera**.

Planen läggs in som en ny plan med alla lager och sina uppgifter. Pluginet kontrollerar efteråt att varje tabell har
lika många rader som filen. Går något fel tas planen bort ur databasen igen, så att inget halvfärdigt blir kvar. Filen
rörs inte. Planen visas markerad i listan, och du öppnar den som vanligt.

En leverans bygger pluginet upp till en plan på samma sätt som *Importera leverans (JSON)*: planområdet, användnings- och
egenskapsytorna med bestämmelser, beslutsinformationen och handlingarna kommer med. Bestämmelser som inte finns i den
laddade planbestämmelsekatalogen hoppas över (ytan skapas ändå), och det som hoppades över visas efter importen.

- **En plan som redan finns skrivs aldrig över.** Finns plan-id:t redan i schemat får du ett felmeddelande. Välj ett
  annat plan-id.
- **Äldre planfiler går bra.** Tabeller som kom i en nyare version blir tomma. En fil gjord med en *nyare* version av
  pluginet än din kan inte importeras: uppdatera pluginet först.
- **Spara planen först** om den är öppen i QGIS, så att alla ändringar finns i filen.

### Exportera planer till filer

1. Markera en eller flera planer i listan (Ctrl eller Skift för flera).
2. Klicka på **Exportera valda** och välj **Som GeoPackage** eller **Som leverans, JSON**, och sedan en mapp.

Varje plan sparas som en fil med planens id som namn (`kv_norr.gpkg` eller `kv_norr.json`). Heter två planer i olika
scheman lika får filen schemats namn först (`dp_a_kv_norr.gpkg`). Planen låses eller checkas inte ut, och en fil som
redan finns i mappen skrivs aldrig över: den planen hoppas över och du får veta det.

Filen visar planen **som den ligger i databasen**. Ändringar som någon har utcheckade men inte checkat in följer inte med.
Ligger databasens schema i en äldre version uppgraderas det först, som när en plan öppnas.

### Kopiera planer

Markera en eller flera planer och klicka på **Kopiera plan…**. Välj databas och schema (ett nytt schema skapas om det
behövs) och, för en enda plan, ett nytt plan-id. Kopian får planens uppgifter och alla objekt, och visar planen som den
ligger i databasen. Flera valda planer behåller sina plan-id, så de måste kopieras till ett annat schema eller en annan
databas. En plan som redan finns skrivs aldrig över.

Det går också att kopiera till en annan databas, till exempel från test till produktion. Planerna måste ha samma
koordinatsystem som schemat de kopieras till.

### Ta bort planer

Markera planerna och klicka på **Ta bort plan…**. Du får bekräfta, och som standard sparas först en
**säkerhetskopia** som GeoPackage i en mapp du väljer (`kv_norr.gpkg`). Går säkerhetskopian inte att spara tas planen inte
bort. Det går **inte att ångra**. Planens alla rader tas bort i en enda transaktion.

En plan som är utcheckad kan inte tas bort, inte heller din egen. Kasta utcheckningen, eller bryt låset (nedan), först.
En plan som är skrivskyddad (nedan) kan inte heller tas bort förrän skyddet bryts.

### Skrivskydda planer som inte får ändras

En detaljplan som har vunnit laga kraft ska normalt inte ändras. Då markerar du planen som **skrivskyddad**:

1. Markera en eller flera planer. Tips: filtrera på *Planstatus: laga kraft* och markera alla.
2. Klicka på **Skrivskydda…**, skriv gärna ett skäl (till exempel *Laga kraft 2026-10-01*) och bekräfta.

Planen får då en sköld i kolumnen *Skrivskydd*, och när du håller musen över den ser du vem som skyddade planen, på vilken
dator, när och varför. En skrivskyddad plan:

- **kan öppnas** (skrivskyddad) och visas i planmosaiken, **exporteras** och **kopieras**. Kopian och exportfilen är nya
  planer utan skrivskydd, så att de går att arbeta vidare med,
- **kan inte checkas ut**, vare sig i databashanteraren eller med knappen *Checka ut* i verktygsfältet. Du får veta vem
  som har skyddat planen och varför,
- **kan inte tas bort**.

Med listan *Alla, med och utan skrivskydd* kan du visa bara de skyddade eller bara de redigerbara planerna.

En utcheckad plan kan inte skrivskyddas: checka in den eller bryt låset först.

#### Bryta skrivskyddet

Behöver en skyddad plan ändras ändå, till exempel vid en ändring av planen, markerar du den och klickar på **Bryt
skrivskydd…**. Du får se vem som skyddade planen och varför, och bekräfta. Planen kan sedan checkas ut och ändras som
vanligt. Skydda den igen när du är klar.

> Skrivskyddet gäller i Rita Detaljplan. Det är ingen behörighetsstyrning i databasen: den som har direkt skrivåtkomst
> till databasen, eller en äldre version av pluginet, kan fortfarande ändra planens tabeller. Vill ni stänga det också
> behöver databasens egna rättigheter sättas för användarna.

### Bryta lås

Är en utcheckning övergiven, till exempel efter en kraschad dator, markerar du planen och klickar på **Bryt lås…**. Du får
se vem som har planen och sedan när, och bekräfta. Den som hade planen utcheckad kan då inte längre checka in sina
ändringar, så gör det bara när du vet att de inte behövs. Samma sak gör **Bryt låset** vid en utcheckning i verktygsfältet.

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
