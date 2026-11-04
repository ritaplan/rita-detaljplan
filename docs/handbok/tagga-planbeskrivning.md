# Tagga planbeskrivning

Programmet **Tagga planbeskrivning** taggar planbeskrivningen (Word, `.docx`) enligt Boverkets föreskrifter BFS 2020:8
och Lantmäteriets Planbeskrivning 2.0. Varje avsnitt får tema, grupp och undergrupp, och motiven kopplas till planens
bestämmelser.

**Originaldokumentet ändras aldrig.**

[![Film: Tagga en planbeskrivning i fyra steg (3 min)](https://ritaplan.xyz/film/detaljplan/tagga-planbeskrivning.jpg)](https://ritaplan.xyz/film/detaljplan/tagga-planbeskrivning.mp4)

## Öppna programmet

Klicka på **Tagga planbeskrivning** (dokumentet med en etikett) i verktygsfältet. Programmet öppnas i ett eget fönster
med den aktiva planen vald. Knappen är grå tills planområdet är ritat.

## Utan QGIS: i webbläsaren

Programmet finns också som webbsida på **[ritaplan.xyz/tagga.html](https://ritaplan.xyz/tagga.html)**. Du behöver varken QGIS
eller någon installation, och **dina filer lämnar aldrig datorn**: sidan läser dem själv i webbläsaren, och originalet
ändras aldrig. Det är samma kod och samma fyra steg som i QGIS. Knappen *Prova med exemplet kv. Lärkan* öppnar en påhittad
plan, om du vill se hur det fungerar först. Webbsidan är en förhandsversion.

Som plankarta väljer du en GeoPackage (`.gpkg`) eller en JSON-leverans (`.json`) i Lantmäteriets format. Ett QGIS-projekt
(`.qgz`) går inte, eftersom webbläsaren inte kommer åt filerna det pekar på. En JSON-leverans saknar planens beteckningar
(e1, a1 …), så programmet kopplar motiven till bestämmelserna på deras text. Står bara beteckningen i planbeskrivningen kan
du koppla motivet själv.

## De fyra stegen

1. **Välj planbeskrivningen** – Word-filen (`.docx`).
2. **Granska taggarna** – pluginet föreslår tema, grupp och undergrupp för varje avsnitt. Ändra där förslaget inte
   stämmer.
3. **Koppla motiven** – koppla motiven i texten till planens bestämmelser. Kartan visar var en bestämmelse gäller.
4. **Kontrollera och spara** – pluginet kontrollerar det obligatoriska innehållet och sparar två kopior.

<!-- BILD: tagga-steg-2.png | Steg 2 i Tagga planbeskrivning: rubrikerna med föreslagna teman -->

## Det här sparas

| Fil | Innehåll |
|---|---|
| **Leveranskopia** | Dokumentet med bokmärken och en XML-del med taggarna. |
| **Granskningskopia** | Dokumentet med taggarna som kommentarer i Word, så att du lätt kan granska dem. |

## Hämta syfte och motiv till planen

Klicka på **Importera till planen** i sista steget. Syftet och motiven från planbeskrivningen läggs då på planen och
dess bestämmelser och ersätter det som stod där. Ändringarna hamnar i redigeringsbufferten, så spara planen som vanligt
efteråt.

Har du ändrat i planen medan fönstret är öppet hämtar **Läs om från QGIS** bestämmelserna igen.

## Så känns rubrikerna igen

Rubrikerna i Word känns igen som tema, grupp och undergrupp när de stämmer med bilagan till föreskrifterna.

- Skiftläge, numrering och skiljetecken spelar ingen roll.
- En liten felstavning går bra. Raden markeras då som *nära*.

### Motiven

Motiv söks **bara** under en rubrik med temat *Motiv till detaljplanens regleringar*. Rubriken känns också igen när
den skrivs på andra vanliga sätt, till exempel *Motiv*, *Motiveringar*, *Motiv till planens bestämmelser* eller *Skäl
till bestämmelserna*.

Hittas inga motiv:

1. Kontrollen säger vilken rubrik som inte känns igen.
2. Välj temat *Motiv till detaljplanens regleringar* för rubriken i listan.
3. Motiven hittas. Valet sparas till nästa dokument med samma rubrik.

#### Motiv under andra rubriker

Står motiven utspridda under andra rubriker, till exempel under varje användning i beskrivningen av planen, söks de inte
av sig själva: då riskerar de att kopplas till fel bestämmelse. I stället pekar du ut rubriken:

1. Markera en rubrik i listan. Har den stycken som pekar ut en bestämmelse (till exempel börjar med bestämmelsens
   beteckning) visas knappen **Räkna som motiv** och hur många stycken som hittades.
2. Klicka på den. Motiven under rubriken (och under rubrikerna under den) hittas nu som motiv.
3. De är **inte kopplade** ännu. Du kopplar dem själv till bestämmelser i steg 3.

Du kan ångra med **Räknas som motiv: ångra**. Valet sparas till nästa dokument med samma rubrik. Rubriken taggas
fortfarande som det tema den har, med motiven som egna bokmärken inuti.
