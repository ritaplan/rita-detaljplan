# Kontrollera planen

Pluginet har två kontroller:

- **Kontrollera planen** granskar hela planen mot Lantmäteriets regler inför leverans.
- **Topologikontroll** hittar små glapp och brytpunkter som nästan, men inte exakt, sammanfaller, och rättar dem.

<!-- FILM: kontrollera | Kontrollera planen och rätta avvikelser, ca 3 min -->

## Kontrollera planen

1. Klicka på **Leverans och export** (brickan med en pil uppåt).
2. Klicka på **Kontrollera planen…** i den blå rutan överst.
3. Gå igenom listan. Avvikelserna är uppdelade i tre slag:
   - **Fel** – stoppar leveransen och måste rättas.
   - **Varningar** – bör ses över, men stoppar inte.
   - **Att fylla i** – uppgifter som saknas.
4. **Dubbelklicka** på en rad för att markera ytan och zooma till den.

Kontrollen körs också automatiskt när du avslutar redigeringen. Resultatet visas då i meddelandefältet.

<!-- BILD: kontrollera-planen.png | Dialogen Kontrollera planen med fel, varningar och att fylla i -->

### Vad som kontrolleras

Bland annat:

- att hela planområdet har en användning (DP-0002/0003),
- överlapp, glapp och smala ytor (DP-Krav-0011–0014),
- självkorsande gränser (DP-Krav-0018),
- att egenskaper ligger inom användningen och har rätt användningsform,
- att varje bestämmelse har rätt värden, värdetyp och enhet (DP-0022/0009),
- tekniska anläggningar (DP-0019/0020),
- att osäkert läge inte anges (DP-0010),
- kraven vid laga kraft: beslutsinformation, handlingar och kvalitetsbeskrivning.

Alla regler finns i [Regler från Lantmäteriets vägledning](../ngp-regler.md).

## Topologikontroll

> Topologikontrollen är i **beta** och har ännu inte full funktionalitet.

Två gränser som nästan, men inte exakt, ligger på varandra ritas båda. Då kan en gräns se olika tjock ut på olika
ställen. Topologikontrollen hittar sådant och föreslår rättningar.

Kontrollen görs på den **sparade** planen. Knappen är grå medan du redigerar: avsluta och spara först.

1. Klicka på **Topologikontroll** (brytpunkter med en cirkel).
2. Välj **tolerans**. Förvalet är 10 cm, som reglerna räknar med. Större avstånd ses som avsiktliga och lämnas orörda.
3. Gå igenom listan. Den har tre avsnitt (se nedan). **Markerar du en rad** ritas dess ändringar direkt i kartan: en
   röd ring där brytpunkten ligger nu, en grön där den hamnar och en linje mellan dem. Ringarna har fast storlek, så att
   en ändring på någon millimeter syns lika tydligt som en på en decimeter. **Visa i kartan** (eller dubbelklick) zoomar
   dessutom till ytan.
4. Kryssa i eller ur raderna. Det säkra är ikryssat, det som ska granskas är det inte.
5. Klicka på **Gör valda ändringar**.
6. Spara genom att avsluta redigeringen.

<!-- BILD: topologikontroll.png | Dialogen Topologikontroll med förslag och Visa i kartan -->

### De tre avsnitten

- **Rättas automatiskt** (högst 1 cm, säkert): ikryssat från början. Det mesta är avrundning som ingen ser.
- **Förslag att granska** (större än 1 cm, upp till toleransen): inte ikryssat. Markera raden, titta i kartan och kryssa i
  det du vill göra. *Markera alla* tar med allt.
- **Kräver ditt beslut:** täckning och överlapp (nedan). Inget av det rättas automatiskt.

### Förslagen

Förslagen står **en rad per yta och avsnitt**, med ytans användningsform (om den har någon), storlek och objektnummer, till exempel
*Egenskapsområde (Kvartersmark, 3 803 m², nr 35): Justera 18 brytpunkter (som mest under 1 mm) mot planområdets gräns*.
Håller du musen över raden ser du varje ändring. Raden gäller hela ytan: kryssar du ur den görs inga av ytans ändringar.

- **Flytta brytpunkter:** en brytpunkt i en användnings- eller egenskapsyta som ligger nära en annan ytas brytpunkt
  eller gräns flyttas dit.
- **Lägg till gemensamma brytpunkter:** ligger en brytpunkt hos planområdet eller en yta som ritades tidigare vid en annan
  ytas gräns, utan att den ytan har en brytpunkt där (en T-skarv), får ytan en brytpunkt där, så att de delar den.
- **Stäng glapp:** glapp mellan ytor stängs. Den yta som ritades senast anpassas till den tidigare. Egenskapsytor
  anpassas på samma sätt till planområdet, användningsytorna och tidigare egenskapsytor.
- **Ta bort dubbletter:** två brytpunkter i rad som ligger inom en centimeter från varandra är en dubblett, och den
  andra tas bort. En yta behåller alltid minst tre brytpunkter.

Avstånd under 1 mm är avrundning som ingen ser, men som ändå gör att två gränser inte ligger exakt på varandra. De
visas som *under 1 mm* och rättas på samma sätt. Planområdet ändras aldrig. Ändringarna görs i redigeringsbufferten med
ett ångra-steg per lager.

### Täckning och överlapp

Under rubriken *Kräver ditt beslut* visas avvikelserna om täckning och överlapp. De är samma kontroller som i *Kontrollera planen*:

- **Planområdet saknar användning** (fel). Knappen *Fyll återstoden med en användningsyta* fyller det som saknas, på
  samma sätt som *Fyll användning*. *Visa i kartan* markerar exakt den del som saknar användning.
- **Användning utanför planområdet** och **användningsområden som överlappar** varandra (fel eller varning, efter storlek).
- **Glapp mellan användningsområden** som är smalare än regeln tillåter, och **egenskap utanför användningen**.
- **Ogiltig gräns:** en yta som korsar sig själv.
- **Ytor utan utbredning** (fel): en yta med area 0, till exempel en spets som går ut och tillbaka längs en gräns och som
  en ritning har lämnat efter sig. Den innehåller ingen information. Knappen **Ta bort tomma ytor** tar bort dem (ett
  ångra-steg per lager). Ytorna räknas inte med bland förslagen om att flytta brytpunkter.

Att en yta saknar bestämmelse, eller att kvartersmark saknar egenskapsområden, visas inte här utan i *Kontrollera planen*.

## Nästa steg

Fortsätt med [Leverera planen](leverera.md).
