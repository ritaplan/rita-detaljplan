# Sätta upp en databas

Den här sidan är för dig som ansvarar för databasen. Du gör stegen **en gång**. Därefter behöver planarkitekterna bara
kunna läsa och skriva. Det gäller från version 0.1.92 av pluginet.

## Det här behövs

- En PostgreSQL-databas med tillägget PostGIS.
- Ett administratörskonto som finns kvar över tid, inte ett personligt. Det kommer att äga tabellerna och behövs vid
  uppgraderingar.
- QGIS med Rita Detaljplan installerat.

## Sätt upp databasen

### 1. Slå på PostGIS

Kör i den databas planerna ska ligga i:

```sql
CREATE EXTENSION postgis;
```

### 2. Lägg in anslutningen i QGIS

Välj *Datakällshanteraren → PostgreSQL → Ny* och anslut med administratörskontot. Använd gärna en
autentiseringskonfiguration, så att lösenordet inte sparas i klartext.

### 3. Skapa schemat och tabellerna

1. Välj **Ny detaljplan…** och **PostGIS-databas** under *Lagras i*.
2. Välj anslutningen och skriv schemat, till exempel `detaljplaner`, och plan-id `uppstart`.
3. Fyll i kommun, mapp och koordinatsystem och skapa planen. Koordinatsystemet gäller sedan alla planer i schemat.
4. Ta bort planen `uppstart` i databashanteraren med **Ta bort plan…**. Tabellerna blir kvar.

### 4. Skapa en grupp som får läsa och skriva

```sql
CREATE ROLE planredaktor NOLOGIN;
GRANT USAGE ON SCHEMA detaljplaner TO planredaktor;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA detaljplaner TO planredaktor;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA detaljplaner TO planredaktor;
ALTER DEFAULT PRIVILEGES IN SCHEMA detaljplaner GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO planredaktor;
ALTER DEFAULT PRIVILEGES IN SCHEMA detaljplaner GRANT USAGE ON SEQUENCES TO planredaktor;
```

De två sista raderna gör att tabeller som tillkommer vid en uppgradering får samma rättigheter. De gäller tabeller som
skapas av kontot som kör raderna, så kör dem med samma konto som i steg 3.

### 5. Lägg till användarna

En rad för varje användare. Har användaren inget konto i databasen skapar du det först, till exempel i pgAdmin.

```sql
GRANT planredaktor TO anna;
```

Ska någon bara titta på planerna räcker `USAGE` på schemat och `SELECT` på tabellerna, till exempel i en egen grupp.

Varje användare installerar sedan pluginet och lägger in anslutningen i QGIS med sitt eget konto.

## Så arbetar planarkitekterna

| Du vill | Gör så här |
|---|---|
| Börja en ny plan | **Ny detaljplan…**, *PostGIS-databas*, schemat `detaljplaner` och ett nytt plan-id |
| Rita | Klicka på **pennan**. Planen checkas ut: den låses och kopieras till din dator |
| Lämna tillbaka | Avsluta redigeringen och klicka på **Checka in** |
| Fortsätta en annan dag | **Öppna**, markera planen och välj **Checka ut och öppna** |
| Bara titta | **Öppna skrivskyddad** eller **Planmosaik…** |
| Skydda en plan som vunnit laga kraft | Markera den i databashanteraren och välj **Skrivskydda…** |

Medan en plan är utcheckad kan ingen annan ändra den, och de ser vem som har den. Läs mer i
[Lagring](lagring.md).

## Löpande

- **Säkerhetskopiera** databasen som ni gör med andra viktiga data.
- **Efter en ny version av pluginet** som ändrar tabellerna får användarna ett meddelande om det. Öppna då en plan en
  gång med administratörskontot.

## Om något går fel

| Meddelandet säger | Det betyder | Gör så här |
|---|---|---|
| *Du har inte rätt att lägga till planer i schemat* | Användaren får inte skriva | Steg 5, och kontrollera steg 4 |
| *Du har inte rätt att skapa tabeller i schemat* | Schemat saknar tabellerna | Steg 3 |
| *Schemat … saknar något som pluginet behöver* | En tabell eller liknande saknas, och bara ägaren får lägga till den | Skapa en plan med administratörskontot |
| *… behöver uppgraderas, men det gick inte* | Tabellerna är från en äldre version | Öppna en plan med administratörskontot |
| *permission denied for table …* | En tabell saknar rättigheter för gruppen | Kör `GRANT`-raderna i steg 4 igen |

## Rättigheter i detalj

Pluginet har ingen egen behörighetsstyrning: databasen avgör vad användaren i QGIS-anslutningen får göra. Alla planer i
ett schema ligger i samma tabeller, så rättigheter sätts per schema, inte per plan.

| Vad man gör | Rättigheter |
|---|---|
| Öppna skrivskyddat, planmosaik, exportera | `USAGE` på schemat, `SELECT` på tabellerna |
| Skapa, importera och kopiera planer i ett schema som har tabellerna, checka ut och in, skrivskydda, ta bort | dessutom `INSERT`, `UPDATE`, `DELETE` på tabellerna och `USAGE` på sekvenserna |
| Skapa schemats tabeller (den första planen) | `CREATE` på schemat, och för att skapa själva schemat `CREATE` på databasen |
| Uppgradera schemat efter en ny version av pluginet | ägarskap av tabellerna |
