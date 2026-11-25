# Leverera planen

Klicka på **Leverans och export** (brickan med en pil uppåt). Dialogen har tre val:

- **Leverera till NGP** – skickar planen till Nationella geodataplattformen.
- **Spara som JSON-fil** – sparar leveransen som en fil.
- **Skapa arkivpaket** – se [Arkivpaket](arkivpaket.md). Det levererar ingenting till NGP.

Överst i en blå ruta visas hur många fel och varningar planen har, med knappen **Kontrollera planen…** (se
[Kontrollera planen](kontrollera.md)).

<!-- BILD: leverans-och-export.png | Dialogen Leverans och export med de tre valen -->

> **Avsluta och spara redigeringen** innan du levererar.

## Spara som JSON-fil

1. Välj **Spara som JSON-fil**.
2. Välj var filen ska sparas.

Filen följer Lantmäteriets format för detaljplan 4.1 (`application/vnd.lm.detaljplan.v4+json`). Den kan till exempel
skickas för granskning eller laddas upp på annat sätt.

Vid exporten

- delas multigeometrier upp i en post per del,
- räknas kopplingen mellan egenskap och användning (`reglerarAnvandningsbestammelse`) fram ur geometrin,
- följer hjälplagren och pluginets egna kolumner inte med,
- skrivs koordinaterna som [öst, nord] med millimeters precision.

> Filen kontrolleras mot Lantmäteriets schema i pluginets tester, men har ännu inte provats i NGP:s
> verifieringsmiljö. Kontrollera i första hand koordinatordningen och ringarnas riktning där.

## Leverera till NGP

> **Kräver producentbehörighet** hos Lantmäteriet. Leveransen är byggd efter Lantmäteriets specifikation men har
> **inte provats mot Lantmäteriets riktiga miljö**. Se [Kända begränsningar](../kanda-begransningar.md).

<!-- FILM: leverera-ngp | Ställ in leveransen och leverera till NGP:s verifieringsmiljö, ca 3 min -->

### Ställ in leveransen första gången

1. Öppna inställningarna med **Inställningar…** i dialogen *Leverans och export*, eller via
   **Rita Detaljplan → Inställning anslutning NGP…**. Dialogen har tre flikar: **Produktion**, **Verifiering** och
   **Sökning**, var och en med egna adresser och egen nyckel.
2. Välj överst vilken miljö **leveransen går till**: *Verifiering* eller *Produktion*. Börja med *Verifiering*.
3. Välj eller skapa en **autentiseringskonfiguration** av typen *Grundläggande autentisering*, med nyckel och
   hemlighet från Lantmäteriets API-portal, på fliken för den miljön. Uppgifterna sparas i QGIS
   autentiseringsdatabas, inte av pluginet. Leverans kräver en nyckel med producentbehörighet.
4. Klicka på **Kontrollera anslutningen**. Pluginet loggar in och ber tjänsten om hälsan, och fliken visar en grön
   prick (aktiv) eller en röd (med förklaring). **Kontrollera alla** prövar alla flikar som har en nyckel.
5. Vill du i databashanteraren kunna se om planerna finns i NGP använder du fliken **Sökning**. Välj där din
   konsumentnyckel för datamängden Detaljplan och vilken miljö du frågar i (se
   [Se om planen finns i NGP](lagring.md#se-om-planen-finns-i-ngp)).

<!-- BILD: ngp-installningar.png | Inställning anslutning NGP med flikarna Produktion, Verifiering och Sökning -->

Dialogen *Leverans och export* öppnas alltid, även innan inställningarna är gjorda. Då är *Leverera till NGP*
avstängt med en förklaring, men *Spara som JSON-fil* fungerar.

### Leverera

1. Välj **Leverera till NGP**.
2. Kontrollera **miljön** och **kommunkoden** (hämtas från planens kommun).
3. Levererar du till **Produktion** måste du kryssa i *Jag förstår att en godkänd plan publiceras i
   produktionsmiljön*.
4. Starta leveransen.

Leveransen körs i bakgrunden. Pluginet registrerar en mottagning, laddar upp planen, väntar på Lantmäteriets
validering och visar sedan status och valideringsrapport.

**Får planen valideringsfel** rättar du felen och levererar igen. Planen laddas då upp på samma mottagning.

> Att uppdatera en plan som redan är publicerad (en ny objektversion) stöds inte ännu.

## Importera en leverans

Har du en plan i Lantmäteriets JSON-format, till exempel från ett annat verktyg som ArcGIS Pro, kan du skapa en ny
plan från den i stället för att rita.

1. Välj **Rita Detaljplan → Importera leverans (JSON)…**. Valet finns bara i menyn.
2. Välj filen.
3. Kommun och planbeteckning föreslås från filen. Välj mapp och koordinatsystem som för en
   [ny plan](kom-igang.md#skapa-en-ny-plan).
4. Spara planen med **disketten** när importen är klar. Den sparas inte automatiskt.

Planområdet, användnings- och egenskapsytorna med bestämmelser, beslutsinformationen och handlingarna kommer med.

Bestämmelser som inte finns i den laddade planbestämmelsekatalogen kan inte läsas in. Ytan skapas ändå, men utan just
den bestämmelsen, och meddelandefältet listar vad som hoppades över.

Ytor, linjer och punkter i flera delar (*multiyta*, *multilinje* och *multipunkt*) läses in. En geometri som pluginet
inte kan läsa hoppas över, och varningen säger vilken bestämmelse det var (formuleringen och objektets identitet).

Anger två bestämmelser av samma slag **olika värden på samma mark**, till exempel största byggnadsarea 25 % och 30 %,
varnar importen med formuleringarna, objektens identiteter och hur stor ytan är. Båda läses in: oftast är en av ytorna fel
i programmet filen kommer ifrån, och ska rättas där. Höjdavgränsningar som inte möts räknas inte, och bestämmelser som
reglerar olika saker (huvudbyggnad och komplementbyggnad) inte heller.

## Nästa steg

- [Teckenförklaring och plankarta](teckenforklaring.md)
- [Arkivpaket](arkivpaket.md)
