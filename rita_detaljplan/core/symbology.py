"""Symbologi för planlagren, byggd på stilbiblioteket "Detaljplaner (Bfs 2020:6)" (CC0, se data/styles).

Hierarkin i kartan: planområdesgräns > användningsgräns > egenskapsgräns. Där gränslinjer sammanfaller ritas bara
den högsta: varje lager ritar sin kantlinje med en geometrigenerator som tar bort de delar som redan ritas av ett
högre lager (och de delar som delas med en annan yta i samma lager, så att en gemensam kant ritas en gång).
Lagerordningen (se ``model.LAYERS``): användningens fyllning ritas underst och egenskapsytornas mönster (t.ex. prickmark)
ovanpå. Användningslagret ritas med blandningsläget Multiplicera mot det som ligger under planen (grundkartan), så att
grundkartans byggnader och gränser syns genom färgen. I en PDF med vektorutskrift finns inget blandningsläge och
användningens färg täcker grundkartan, men egenskapernas mönster ligger ovanpå och syns.

  * Användningsytor färgas efter Boverkets färgnamn (Gul, Blågrå, …).
  * Egenskapsytor är genomskinliga; bestämmelser med symbol i Boverkets katalog (t.ex. prickmark) får mönstret.
  * Egenskapslinjer (utfartsförbud, stängsel) får sina symboler.
  * Ytor och objekt som ännu saknar bestämmelse ritas med ett tydligt snedstreck, så att man ser vad som återstår.
  * Beteckningen (t.ex. R1, e2) skrivs ut som etikett.

Katalogens färgnamn saknar färgkoder; ``FARGER`` avgör vilken färg varje namn får och kan justeras.
"""
from __future__ import annotations

from pathlib import Path

from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsFillSymbolLayer,
    QgsFontMarkerSymbolLayer,
    QgsGeometryGeneratorSymbolLayer,
    QgsLinePatternFillSymbolLayer,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointPatternFillSymbolLayer,
    QgsProperty,
    QgsRenderContext,
    QgsRendererCategory,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsSymbolLayer,
    QgsTemplatedLineSymbolLayerBase,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter

STYLE_FILE = Path(__file__).resolve().parent.parent / "data" / "styles" / "detaljplaner-bfs-2020-6.xml"

# Boverkets färgnamn -> färg. Färgnamnen och vilka användningar som har dem följer BFS 2020:6. Kulörerna är användarens
# palett (kolumnen Kulör i tabellen över användningar), mappad till färgnamnen: ljusa och dämpade färger där ingen tar över
# kartan (OKLCH-ljushet 0,73 till 0,92, mättnad högst 0,12, inget färgpar närmare än 5, OKLab gånger 100). Rosa (Y, annan
# kvartersmark) saknas i tabellen och är oförändrad. Parkering på kvartersmark (P) är Grå enligt BFS 2020:6 och får därför
# gråns färg, inte den ljusare grå (#dce0dd) som tabellen anger för P.
FARGER: dict[str, tuple[int, int, int]] = {
    "Gul": (255, 228, 133),
    "Brun": (179, 169, 148),
    "Beige": (220, 207, 166),
    "Orange": (235, 181, 127),
    "Röd": (219, 154, 142),
    "Rosa": (249, 180, 191),
    "Lila": (195, 177, 214),
    "Blå": (169, 207, 234),
    "Blågrå": (154, 172, 184),
    "Grön": (143, 203, 138),
    "Ljusgrön": (169, 224, 155),
    "Grå": (187, 191, 189),
    "Ljusgrå": (220, 224, 221),
}
FALLBACK_FARG = (245, 245, 245)
UNASSIGNED = "ej tilldelad"  # klassvärde för objekt som ännu saknar bestämmelse
UNASSIGNED_COLOR = (220, 90, 40)

# Uttryck som ger klassen för varje objekt: "ej tilldelad" så länge bestämmelse saknas.
_USE_CLASS = f"CASE WHEN coalesce(\"bestammelser\", 0) = 0 THEN '{UNASSIGNED}' ELSE coalesce(\"farg\", '') END"
_UNASSIGNED_CLASS = f"CASE WHEN coalesce(\"bestammelser\", 0) = 0 THEN '{UNASSIGNED}' ELSE '' END"

# Boverkets symbolnamn -> symbol i stilbiblioteket, när namnen skiljer sig åt.
SYMBOL_ALIAS = {
    "Marken får inte förses med byggnad/byggnadsverk":
        "Marken får inte förses med byggnadsverk eller viss typ av byggnadsverk",
}
AREA_SYMBOLS = (
    "Marken får endast förses med byggnadsverk under mark",
    "Marken får endast förses med viss typ av byggnadsverk",
    "Marken får inte förses med byggnad/byggnadsverk",
)
LINE_SYMBOLS = ("Utfart får inte finnas", "Stängsel ska finnas")
# Symboler som ritas som linje längs ytans kant i stället för som fyllning (indelning i fastigheter, Boverket)
OUTLINE_SYMBOLS = ("Fastighetsindelning",)


def _has_symbol(name: str) -> str:
    """Uttryck: ytans eller linjens symbolfält innehåller symbolen (fältet kan ha flera, åtskilda av ``|``)."""
    return f"array_contains(string_to_array(coalesce(\"symbol\", ''), '|'), '{name}')"


def _symbol_class(names: tuple[str, ...]) -> str:
    """Klassen för ett objekt med flera symboler: den första av ``names`` som objektet har, annars ''. Ett objekt kan ha
    både korsmark och fastighetsindelning; fyllningen väljs här och kantlinjen läggs till separat."""
    cases = " ".join(f"WHEN {_has_symbol(name)} THEN '{name}'" for name in names)
    return f"CASE WHEN coalesce(\"bestammelser\", 0) = 0 THEN '{UNASSIGNED}' ELSE CASE {cases} ELSE '' END END"


_AREA_CLASS = _symbol_class(AREA_SYMBOLS)
_LINE_CLASS = _symbol_class(LINE_SYMBOLS)
_DIVISION = _has_symbol("Fastighetsindelning")  # ytan har bestämmelsen indelning i fastigheter

def load_style(path: Path = STYLE_FILE) -> QgsStyle:
    style = QgsStyle()
    if not style.importXml(str(path)):
        raise ValueError(f"Kunde inte läsa stilbiblioteket {path}")
    return style


MIN_DASH_GAP = 0.05  # punkter: en kortare lucka i ett streckmönster räknas som noll och tas bort (se _clean_dash_pattern)


def _clean_dash_pattern(layer) -> None:
    """Tar bort luckor på (nästan) noll längd ur ett eget streckmönster, utan att linjen ser annorlunda ut.

    Stilbiblioteket skriver planområdesgränsen som ``8;4;4;4;16;4;8;1e-06``: den sista luckan på 0,000001 pt gör att ett
    sista streck på 8 sammanfogas med det första i nästa period (8 + 8 = 16). QGIS skriver in det i en PDF som en
    lucka på 0,0001. Här slås strecken som luckan skiljde åt ihop i stället, och mönstret förskjuts så att linjen börjar
    likadant: ``16;4;4;4;16;4`` med förskjutning 8."""
    if not isinstance(layer, QgsSimpleLineSymbolLayer) or not layer.useCustomDashPattern():
        return
    pattern = [float(v) for v in layer.customDashVector()]
    if len(pattern) < 2 or len(pattern) % 2:
        return
    offset = layer.dashPatternOffset()
    same_unit = layer.customDashPatternUnit() == layer.dashPatternOffsetUnit()
    while len(pattern) >= 2:
        tiny = next((i for i in range(1, len(pattern), 2) if pattern[i] < MIN_DASH_GAP), None)
        if tiny is None:
            break
        if len(pattern) == 2:  # bara ett streck och ingen riktig lucka: heldragen linje
            layer.setUseCustomDashPattern(False)
            return
        if tiny + 1 < len(pattern):  # streck före och efter luckan blir ett
            pattern = pattern[:tiny - 1] + [pattern[tiny - 1] + pattern[tiny + 1]] + pattern[tiny + 2:]
        elif same_unit:  # sista luckan: sista och första strecket blir ett, och mönstret börjar med det
            last = pattern[-2]
            pattern = [last + pattern[0]] + pattern[1:-2]
            offset += last
        else:  # annan enhet på förskjutningen: nöj dig med en synlig lucka
            pattern[tiny] = MIN_DASH_GAP
    layer.setCustomDashVector(pattern)
    layer.setDashPatternOffset(offset)


def _tidy(symbol):
    """Gör en symbol stabil på kartan och i utskrift.

    * Utan klippning mot kartrutan: annars räknas mönstrets utgångspunkt och streckens fas om från den synliga delen, så
      prick- och plusmark och streckade linjer "hoppar" när man panorerar eller zoomar.
    * Punktmönster (prickmark, plusmark, ringprickad mark) klipps inte mot ytans form: en markör ritas hel om dess
      mittpunkt ligger inom ytan, så inga halva prickar, ringar eller plustecken syns längs kanterna.
    * Streckade linjer: mönstret justeras inte efter linjens längd och hörn (``alignDashPattern``) och har inga luckor på
      noll längd (``_clean_dash_pattern``). Annars skriver QGIS in en strecksats per linje i en PDF med vektorutskrift,
      med tiotals tal och en sista lucka på 0,0001, och Acrobat vägrar spara sidan som bild ("Streckargument är
      ogiltiga"). Utan justeringen blir satsen kort (4 till 6 tal) och likadan för alla linjer."""
    if symbol is None:
        return symbol
    symbol.setClipFeaturesToExtent(False)
    for layer in symbol.symbolLayers():
        _clean_dash_pattern(layer)
        if isinstance(layer, QgsSimpleLineSymbolLayer):
            layer.setAlignDashPattern(False)
            layer.setTweakDashPatternOnCorners(False)
        if isinstance(layer, QgsPointPatternFillSymbolLayer):
            layer.setClipMode(Qgis.MarkerClipMode.CentroidWithin)
        inner = layer.subSymbol() if hasattr(layer, "subSymbol") else None
        if inner is not None:
            _tidy(inner)
    return symbol


def _plus_marker(size_pt: float = 3.6, width_pt: float = 0.45):
    """Ett plustecken som vanlig markör (ingen typsnittsberoende glyf): ser likadant ut på alla datorer och i PDF."""
    marker = QgsSimpleMarkerSymbolLayer(Qgis.MarkerShape.Cross, size_pt, 0.0, Qgis.ScaleMethod.ScaleDiameter,
                                        QColor(0, 0, 0), QColor(0, 0, 0))
    marker.setSizeUnit(Qgis.RenderUnit.Points)
    marker.setStrokeWidth(width_pt)
    marker.setStrokeWidthUnit(Qgis.RenderUnit.Points)
    return marker


def _robust_pattern(symbol):
    """Byter typsnittsmarkörer med plustecken (plusmark) mot en riktig kryssmarkör. Typsnittet i stilbiblioteket
    (Noto Sans) finns inte på alla datorer och ger då fel tecken eller rutor."""
    for layer in symbol.symbolLayers():
        inner = layer.subSymbol() if isinstance(layer, QgsPointPatternFillSymbolLayer) else None
        if inner is None:
            continue
        for index, marker in enumerate(inner.symbolLayers()):
            if isinstance(marker, QgsFontMarkerSymbolLayer) and marker.character().strip() == "+":
                inner.changeSymbolLayer(index, _plus_marker())
    return symbol


def _symbol(style: QgsStyle, name: str):
    return style.symbol(SYMBOL_ALIAS.get(name, name))


def _outline_from(style: QgsStyle, name: str):
    """Ett linjesymbolskikt ur stilbiblioteket, att lägga som kant på en yta."""
    line = style.symbol(name)
    return line.symbolLayer(0).clone() if line is not None and line.symbolLayerCount() else None


COINCIDENCE_TOLERANCE = 0.05  # meter: kantlinjer närmare än så räknas som sammanfallande
_EMPTY = "geom_from_wkt('GEOMETRYCOLLECTION EMPTY')"


def hierarchical_boundary(layers: dict[str, QgsVectorLayer], own_table: str, higher_tables: tuple[str, ...],
                          same_kind: bool = False) -> str:
    """Uttryck för kantlinjen av en yta utan det som redan ritas av högre lager eller av en annan yta i samma lager.

    Delade kanter inom lagret ritas av ytan med lägst ``objektidentitet``, så att de inte ritas två gånger. Med
    ``same_kind`` döljer bara ytor av samma slag varandra (``sekundar``): egenskapsgränser och sekundära
    egenskapsgränser ritas ovanpå varandra där de sammanfaller (BFS 2020:6, 3.3)."""
    # Toleransen följer planens storlek så att en mycket liten plan inte får hela kanter bortdöljda; för en vanlig plan
    # blir den COINCIDENCE_TOLERANCE.
    plan = layers.get("detaljplan")
    if plan is not None:
        tolerance = (f"min({COINCIDENCE_TOLERANCE}, max(0.000001, 0.0005 * "
                     f"sqrt(coalesce(aggregate('{plan.id()}', 'sum', $area), 1000000))))")
    else:
        tolerance = str(COINCIDENCE_TOLERANCE)
    # Bara ytor närmare än toleransen kan dölja något av kanten, så bara de hämtas (overlay_nearest, med ett spatialt
    # index som byggs en gång). Ett aggregat med filter på @parent räknar om alla ytor för varje yta och blir mycket
    # långsamt för stora planer.
    # limit:=-1 ger bara de ytor som rör vid varandra och hoppar över max_distance, så en smal glugg under toleransen
    # missas: ett stort tal ger alla grannar inom toleransen.
    nearby = f"max_distance:={tolerance}, limit:=1000, cache:=true"
    hidden = [f"coalesce(boundary(collect_geometries(overlay_nearest('{layers[table].id()}', $geometry, {nearby}))), "
              f"{_EMPTY})" for table in higher_tables if table in layers]
    # Grannarna i det egna lagret: bara de med lägre objektidentitet (och, med ``same_kind``, samma slag) döljer ytan.
    values = '"objektidentitet", coalesce("sekundar", 0), $geometry' if same_kind else '"objektidentitet", $geometry'
    geometry_position = 2 if same_kind else 1
    only_earlier = '"objektidentitet" > array_get(@element, 0)'
    if same_kind:
        only_earlier += ' AND coalesce("sekundar", 0) = array_get(@element, 1)'
    neighbours = f"overlay_nearest('{layers[own_table].id()}', array({values}), {nearby})"
    hidden.append(f"coalesce(boundary(collect_geometries(array_foreach(array_filter({neighbours}, {only_earlier}), "
                  f"array_get(@element, {geometry_position})))), {_EMPTY})")
    return (f"difference(boundary($geometry), buffer(collect_geometries({', '.join(hidden)}), {tolerance}))")


def _generated_outline(style: QgsStyle, symbol_name: str, expression: str):
    """Ett linjeskikt som ritar ``expression`` (en linjegeometri) med en linjesymbol ur stilbiblioteket."""
    line = style.symbol(symbol_name)
    if line is None:
        return None
    generator = QgsGeometryGeneratorSymbolLayer.create({"geometryModifier": expression, "SymbolType": "Line"})
    generator.setSubSymbol(_tidy(line.clone()))
    return generator


def _append_outlines(symbol, outline) -> None:
    """Lägger kantlinjeskikten (ett skikt, eller flera i en lista) överst på symbolen."""
    for layer in (outline if isinstance(outline, (list, tuple)) else [outline]):
        if layer is not None:
            symbol.appendSymbolLayer(layer)


def _fill(color: tuple[int, int, int] | None, outline=None) -> QgsFillSymbol:
    """Fyllning (eller genomskinlig) utan penna; kantlinjen är ett linjeskikt (``outline``) från stilbiblioteket."""
    symbol = QgsFillSymbol()
    symbol.deleteSymbolLayer(0)
    base = QgsSimpleFillSymbolLayer(QColor(*color) if color else QColor(0, 0, 0, 0))
    base.setStrokeStyle(Qt.PenStyle.NoPen)
    symbol.appendSymbolLayer(base)
    _append_outlines(symbol, outline)
    return _tidy(symbol)


def _hatched(color: tuple[int, int, int], background: tuple[int, int, int] | None = None, outline=None) -> QgsFillSymbol:
    """Snedstreck: markerar ytor som ännu saknar bestämmelse."""
    symbol = _fill(background, None)
    hatch = QgsLinePatternFillSymbolLayer()
    hatch.setLineAngle(45)
    hatch.setDistance(2.2)
    hatch.setColor(QColor(*color))
    hatch.setLineWidth(0.3)
    symbol.appendSymbolLayer(hatch)
    _append_outlines(symbol, outline)
    return _tidy(symbol)


SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
# Siffror i beteckningar ritas nedsänkta (e₁, R₂). Lagrat värde (e1) ändras inte, bara visningen.
# Ett ord med kolon är ett lutningsförhållande (1:20): det ritas som det står, utan nedsänkta siffror.
_SUBSCRIPT_EXPRESSION = (
    "array_to_string(array_foreach(string_to_array(coalesce(\"beteckning\", ''), ' '), "
    "if(@element LIKE '%:%', @element, replace(@element, "
    f"array({', '.join(repr(d) for d in '0123456789')}), array({', '.join(repr(d) for d in SUBSCRIPT_DIGITS)})))), ' ')")


# Egenskapspunkter för markens höjd visar höjden ("+31,8"): den får inte nedsänkta siffror som en beteckning (e₁)
_POINT_LABEL_EXPRESSION = (f"CASE WHEN left(coalesce(\"beteckning\", ''), 1) IN ('+', '-') THEN \"beteckning\" "
                           f"ELSE {_SUBSCRIPT_EXPRESSION} END")
POINT_MARKER_MM = 0.9  # punktens storlek (diameter, mm på papper i referensskalan)
POINT_LABEL_DISTANCE_MM = 0.8  # avstånd mellan punkten och dess text

USE_TEXT_MM = 6.0  # användningsbestämmelsens textstorlek (mm på papper i referensskalan)
PROPERTY_TEXT_MM = 3.5  # egenskapsbestämmelsernas: tydligt mindre än användningens
CHAR_WIDTH = 0.62  # ungefärlig medelbredd på ett tecken i fet stil, i delar av textstorleken (för radbrytning)


# Ytans delar. De flesta ytor har en; en bestämmelse som gäller flera skilda ytor har flera, och varje del får sin text.
_PARTS = "geometries_to_array($geometry)"
# Texten på en del (@element): där användaren flyttat den (@own = ``label_x``/``label_y``), annars delens textpunkt, som är
# tyngdpunkten om den ligger i delen och annars en punkt inne i den. Ytan har bara ett sparat textläge, så en flyttad text
# ersätter texten på den del som ligger närmast det nya läget; andra delar behåller sin.
_TEXT_POINT = ("CASE WHEN distance(@element, @own) <= distance($geometry, @own) + 0.001 THEN @own "
               "WHEN intersects(centroid(@element), @element) THEN centroid(@element) "
               "ELSE point_on_surface(@element) END")


def _in_each_part(expression: str) -> str:
    """Uttrycket en gång för varje del av ytan (``@element`` är delen, ``@own`` det flyttade textläget eller tomt), samlat
    till en geometri. Samma uttryck för en och flera delar: QGIS tolkar uttryckens text på nytt vid varje omritning, så
    de ska vara så korta det går."""
    return ("with_variable('own', make_point(\"label_x\", \"label_y\"), "
            f"collect_geometries(array_foreach({_PARTS}, {expression})))")


def _place_at_point(settings: QgsPalLayerSettings) -> None:
    """Ytans text står på en fast punkt: det läge användaren flyttat den till (``label_x``/``label_y``), annars ytans textpunkt
    (``_TEXT_POINT``). En yta i flera delar får en text på varje del. Punkten är etikettens egen geometri (en
    geometrigenerator), inte ett datadefinierat läge: QGIS struntar i ett datadefinierat läge som ligger utanför det synliga
    kartutsnittet och lägger då texten på ytans automatiska plats, så en text som flyttats för hand hoppade när man zoomade
    in. Texten är centrerad på punkten."""
    settings.geometryGenerator = _in_each_part(_TEXT_POINT)
    settings.geometryGeneratorType = Qgis.GeometryType.Point
    settings.geometryGeneratorEnabled = True


def _move_by_fields(settings: QgsPalLayerSettings) -> None:
    """Texten placeras automatiskt, men på det läge användaren flyttat den till om ``label_x``/``label_y`` är satta (för en
    linje; ytornas texter se ``_place_at_point``)."""
    props = settings.dataDefinedProperties()
    props.setProperty(QgsPalLayerSettings.Property.PositionX, QgsProperty.fromField("label_x"))
    props.setProperty(QgsPalLayerSettings.Property.PositionY, QgsProperty.fromField("label_y"))
    for prop, value in ((QgsPalLayerSettings.Property.Hali, "Center"), (QgsPalLayerSettings.Property.Vali, "Half")):
        props.setProperty(prop, QgsProperty.fromExpression(
            f"CASE WHEN \"label_x\" IS NULL OR \"label_y\" IS NULL THEN NULL ELSE '{value}' END"))
    settings.setDataDefinedProperties(props)


def _rotate_by_field(settings: QgsPalLayerSettings) -> None:
    """Texten är vågrät, men vinklad (grader medurs, runt textens mitt) om användaren roterat den med textverktyget:
    ``label_rot`` är tomt när den inte roterats. Gäller ytornas texter (en linjes text följer linjen, en punkts text står
    alltid intill punkten)."""
    props = settings.dataDefinedProperties()
    props.setProperty(QgsPalLayerSettings.Property.LabelRotation, QgsProperty.fromExpression(
        f'CASE WHEN {_has_symbol(SLOPE_SYMBOL)} THEN {_slope_text_angle()} ELSE "label_rot" END'))
    settings.setDataDefinedProperties(props)


def _wrap_by_width(settings: QgsPalLayerSettings, size: float, fit_area: bool = True) -> None:
    """Texten radbryts efter textrutans bredd (``label_w``) om användaren omformat den. Annars radbryts den så att den
    ryms i ytan (``fit_area``), eller inte alls. En yta i flera delar får samma radbrytning på alla delar, så att texten
    ryms i den smalaste. ``size`` = textstorleken i kartans enheter. Bara ord bryts, aldrig bokstäver."""
    per_char = size * CHAR_WIDTH
    width = f"array_min(array_foreach({_PARTS}, bounds_width(@element)))"
    otherwise = f"max(3, floor({width} * 0.9 / {per_char}))" if fit_area else "0"  # 0 = ingen radbrytning
    props = settings.dataDefinedProperties()
    props.setProperty(QgsPalLayerSettings.Property.AutoWrapLength, QgsProperty.fromExpression(
        f'CASE WHEN "label_w" IS NOT NULL THEN max(1, floor("label_w" / {per_char})) ELSE {otherwise} END'))
    settings.setDataDefinedProperties(props)
    settings.useMaxLineLengthForAutoWrap = True


SLOPE_SYMBOL = "Största/minsta lutning"  # se rows.SLOPE_SYMBOL
SLOPE_ARROW_MIN_MM = 7.0  # pilens minsta längd (mm på papper i referensskalan); den är annars lika lång som texten
SLOPE_ARROW_GAP_MM = 0.6  # luft mellan texten och pilen
SLOPE_ARROW_LINE_MM = 0.25
SLOPE_ARROW_HEAD_MM = 1.8


def _slope_text_angle() -> str:
    """Textens vinkel (grader medurs) för en yta med lutningspil: den lagrade vinkeln, men aldrig upp och ned. Pilen pekar åt
    det håll vinkeln anger, så en pil som pekar åt vänster (180 grader) har ändå texten rättvänd ovanför sig."""
    return ("CASE WHEN coalesce(\"label_rot\", 0) >= 90 AND coalesce(\"label_rot\", 0) < 270 "
            "THEN \"label_rot\" - 180 ELSE coalesce(\"label_rot\", 0) END")


def _slope_arrow_geometry(size: float, minimum: float, gap: float) -> str:
    """Lutningspilen som linje (ett uttryck för en geometrigenerator): under ytans text, lika lång som texten (minst
    ``minimum``) och riktad åt det håll textens vinkel (``label_rot``) anger, vågrätt åt höger när den inte vridits. En yta
    i flera delar får en pil under texten på varje del. Tom för ytor utan symbolen. Pilen ligger på det håll som marken
    stiger uppåt (BFS 2020:6, 7.2 och 7.13). ``size``, ``minimum`` och ``gap`` är i kartans enheter."""
    length = f"max({minimum}, length(coalesce(\"beteckning\", '')) * {size * CHAR_WIDTH})"
    below = f"{size * TEXT_HEIGHT} + {gap}"  # från textens mitt till pilen

    middle = f"project({_TEXT_POINT}, {below}, radians({_slope_text_angle()}) + pi())"  # rakt under den vridna texten
    along = "radians(coalesce(\"label_rot\", 0) + 90)"  # pilens riktning, som azimut (medurs från norr)
    half = f"{length} / 2"
    arrow = f"with_variable('m', {middle}, make_line(project(@m, -{half}, {along}), project(@m, {half}, {along})))"
    return f"CASE WHEN {_has_symbol(SLOPE_SYMBOL)} THEN {_in_each_part(arrow)} ELSE {_EMPTY} END"


def _slope_arrow_layer(reference_scale: float, size_mm: float):
    """Lutningspilen (se ``_slope_arrow_geometry``): en tunn svart linje med en fylld pilspets i änden."""
    per_mm = reference_scale / 1000.0
    generator = QgsGeometryGeneratorSymbolLayer.create({
        "geometryModifier": _slope_arrow_geometry(size_mm * per_mm, SLOPE_ARROW_MIN_MM * per_mm,
                                                  SLOPE_ARROW_GAP_MM * per_mm),
        "SymbolType": "Line"})
    shaft = QgsSimpleLineSymbolLayer(QColor(0, 0, 0))
    shaft.setWidth(SLOPE_ARROW_LINE_MM)
    shaft.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    head = QgsMarkerLineSymbolLayer()
    head.setPlacements(QgsTemplatedLineSymbolLayerBase.Placement.LastVertex)
    head.setRotateSymbols(True)
    marker = QgsMarkerSymbol.createSimple({"name": "triangle", "color": "0,0,0", "outline_style": "no",
                                           "size": str(SLOPE_ARROW_HEAD_MM), "angle": "90"})
    head.setSubSymbol(marker)
    arrow = QgsLineSymbol()
    arrow.deleteSymbolLayer(0)
    arrow.appendSymbolLayer(shaft)
    arrow.appendSymbolLayer(head)
    generator.setSubSymbol(arrow)
    return generator


LEADER_INSET_MM = 3.5  # hur långt in i ytan ledlinjen slutar (mm på papper i referensskalan)
LEADER_GAP_MM = 0.4  # luft mellan ledlinjens yttre ände och texten (mm på papper i referensskalan)
TEXT_HEIGHT = 0.6  # textrutans halva höjd, i delar av textstorleken (för ledlinjens ände vid texten)


def _leader_geometry(inset: float, size: float, gap: float) -> str:
    """Ledlinjen från en text som flyttats utanför sin yta in till ytan, som ett uttryck för en geometrigenerator. Linjen går
    från en punkt ``inset`` (kartans enheter) innanför ytans gräns, rakt mot textens läge (dock aldrig längre in än ytans
    mitt), och slutar ``gap`` utanför textrutan så att den inte går genom texten. Tom när texten inte flyttats eller ligger
    inne i ytan. ``size`` är textstorleken i kartans enheter. Textrutans mått uppskattas ur textens längd (eller textrutans
    bredd, ``label_w``). Har ytan flera delar går linjen till den del som ligger närmast texten.

    Ledlinjen är ett linjeskikt i ytans symbol, inte en callout: en callout ritas inte för en text som har en egen punkt som
    geometri (se ``_place_at_point``)."""
    half_width = ("coalesce(\"label_w\", length(coalesce(\"beteckning\", '')) * " + str(size * CHAR_WIDTH) + ") / 2")
    text_at = 'make_point("label_x", "label_y")'  # upprepas hellre än läggs i en variabel, se nedan
    direction = f"azimuth({text_at}, @a)"
    exit_distance = (f"min(({half_width}) / max(abs(sin({direction})), 0.001), "
                     f"{size * TEXT_HEIGHT} / max(abs(cos({direction})), 0.001)) + {gap}")
    nearest_part = f"array_first(array_filter({_PARTS}, distance(@element, @gr) < 0.001))"
    # @gr = ytans närmaste punkt, @a = punkten inne i den delen där linjen slutar. Bara två variabler: QGIS tolkningstid
    # fördubblas för varje nivå som with_variable nästlas, och uttrycket tolkas på nytt vid varje omritning.
    end = (f"end_point(line_substring(make_line(@gr, coalesce(pole_of_inaccessibility({nearest_part}, 0.1), @gr)), "
           f"0, {inset}))")
    return ("CASE WHEN \"label_x\" IS NULL OR \"label_y\" IS NULL THEN " + _EMPTY +
            f" WHEN intersects($geometry, {text_at}) THEN {_EMPTY} ELSE "
            f"with_variable('gr', closest_point($geometry, {text_at}), with_variable('a', {end}, "
            f"make_line(@a, line_interpolate_point(make_line({text_at}, @a), "
            f"min({exit_distance}, distance({text_at}, @a)))))) END")


def _leader_layer(reference_scale: float, size_mm: float):
    """Tunn svart ledlinje (se ``_leader_geometry``), för en yta vars text flyttats utanför den."""
    per_mm = reference_scale / 1000.0  # meter i kartan per mm på papper
    generator = QgsGeometryGeneratorSymbolLayer.create({
        "geometryModifier": _leader_geometry(LEADER_INSET_MM * per_mm, size_mm * per_mm, LEADER_GAP_MM * per_mm),
        "SymbolType": "Line"})
    generator.setSubSymbol(QgsLineSymbol.createSimple({"color": "0,0,0", "width": "0.15", "width_unit": "MM",
                                                       "capstyle": "flat"}))
    return generator


def _with_leader(symbol, reference_scale: float, size_mm: float):
    """Ytans symbol med ledlinjen överst."""
    symbol.appendSymbolLayer(_leader_layer(reference_scale, size_mm))
    return symbol


def _labeling(reference_scale: float = 1000, *, bold: bool = True, is_use: bool = False,
              is_line: bool = False, is_point: bool = False) -> QgsVectorLayerSimpleLabeling:
    """Etikett för beteckningen. Storleken är fast i referensskalan (angiven i meter i kartan), så texten blir
    inte orimligt stor eller liten när man zoomar. Användningens etikett ligger mitt i ytan, tvingas in i ytan och
    visas alltid; egenskapernas är mindre, ligger inom sin egen yta (radbrutna efter ytans bredd) och viker undan för
    användningens."""
    per_mm = reference_scale / 1000.0  # meter i kartan per mm på papper
    size_mm = USE_TEXT_MM if is_use else PROPERTY_TEXT_MM
    settings = QgsPalLayerSettings()
    settings.fieldName = _SUBSCRIPT_EXPRESSION
    settings.isExpression = True
    settings.enabled = True
    font = QFont()
    font.setBold(bold)
    fmt = QgsTextFormat()
    fmt.setFont(font)
    fmt.setSizeUnit(Qgis.RenderUnit.Millimeters)
    fmt.setSize(size_mm)
    fmt.buffer().setEnabled(True)
    fmt.buffer().setSizeUnit(Qgis.RenderUnit.Millimeters)
    fmt.buffer().setSize(0.25)
    fmt.buffer().setColor(QColor(255, 255, 255))
    settings.setFormat(fmt)
    if not is_point:  # en egenskapspunkts text kan inte flyttas: den står alltid intill punkten
        if is_line:
            _move_by_fields(settings)
        else:
            _place_at_point(settings)
            _rotate_by_field(settings)
    if is_point:
        # texten intill punkten (helst snett ovanför till höger), som höjder på en plankarta
        settings.fieldName = _POINT_LABEL_EXPRESSION
        settings.placement = Qgis.LabelPlacement.AroundPoint
        settings.dist = POINT_LABEL_DISTANCE_MM
        settings.distUnits = Qgis.RenderUnit.Millimeters
        settings.priority = 4
        settings.obstacleSettings().setIsObstacle(False)
        return QgsVectorLayerSimpleLabeling(settings)
    if is_line:
        settings.labelPerPart = True  # en linje i flera delar får text på varje del (ytorna: se _place_at_point)
        settings.placement = Qgis.LabelPlacement.Line
        settings.priority = 3
        settings.obstacleSettings().setIsObstacle(False)
        return QgsVectorLayerSimpleLabeling(settings)
    if not is_use:
        # Fast plats: mitt i den egna ytan (en punkt inne i hela ytan, inte i den del som syns), radbruten efter ytans bredd.
        # Med ``Horizontal`` letade QGIS en plats i den synliga delen av ytan, så texten hoppade när man panorerade eller
        # zoomade. Vill man ha den någon annanstans flyttar man den (``label_x``, ``label_y``).
        settings.placement = Qgis.LabelPlacement.OverPoint
        settings.centroidInside = True
        settings.centroidWhole = True
        settings.placementSettings().setOverlapHandling(Qgis.LabelOverlapHandling.AllowOverlapIfRequired)
        settings.priority = 3
        settings.obstacleSettings().setIsObstacle(False)  # egenskapsytan får inte trycka undan användningens etikett
        _wrap_by_width(settings, size_mm * per_mm)
        return QgsVectorLayerSimpleLabeling(settings)
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.centroidInside = True  # punkten tvingas in i ytan även för konkava och smala former
    settings.centroidWhole = True
    settings.displayAll = True  # användningens text visas även när något annat ligger i vägen
    settings.priority = 10
    settings.zIndex = 10.0
    _wrap_by_width(settings, size_mm * per_mm, fit_area=False)  # radbryts bara om textrutan omformats
    return QgsVectorLayerSimpleLabeling(settings)


def _apply_labels(layer: QgsVectorLayer, reference_scale: float, **kwargs) -> None:
    layer.setLabeling(_labeling(reference_scale, **kwargs))
    layer.setLabelsEnabled(True)


FILL_PASS, OUTLINE_PASS = 0, 1


def _outlines_last(renderer) -> None:
    """Ritar alla fyllningar först och alla kantlinjer efteråt, över alla ytor i lagret (symbolnivåer).

    Annars ritas varje yta för sig, fyllning och kant i följd, och en gemensam kant (som bara en av två grannar
    ritar) täcks till hälften av grannens fyllning om grannen råkar ritas sist: gränsen blir hälften så bred och
    vilken yta som drabbas beror på ordningen i filen, så det kan ändras när projektet sparas."""
    symbols = [s for s in renderer.symbols(QgsRenderContext()) if s.type() == Qgis.SymbolType.Fill]
    for symbol in symbols:
        for layer in symbol.symbolLayers():
            layer.setRenderingPass(FILL_PASS if isinstance(layer, QgsFillSymbolLayer) else OUTLINE_PASS)
    if symbols:
        renderer.setUsingSymbolLevels(True)


def labels_in_millimeters(layer: QgsVectorLayer) -> bool:
    """Om lagrets texter anges i millimeter (som linjerna, så att de skalas lika när man zoomar). Äldre planer har texterna
    i kartenheter, som skalades en gång för mycket med referensskalan."""
    labeling = layer.labeling()
    settings = labeling.settings() if labeling is not None and hasattr(labeling, "settings") else None
    return settings is None or settings.format().sizeUnit() == Qgis.RenderUnit.Millimeters


def has_fixed_label_position(layer: QgsVectorLayer, table: str) -> bool:
    """Om ytornas texter har en fast plats, oberoende av vilken del av kartan som syns (ett projekt som sparats av en äldre
    version lät QGIS välja plats i den synliga delen av ytan, eller ignorera ett flyttat läge som låg utanför kartutsnittet,
    så texten hoppade när man zoomade eller flyttade kartan; se ``_place_at_point``)."""
    if table not in ("anvandning_yta", "egenskap_yta"):
        return True
    labeling = layer.labeling()
    settings = labeling.settings() if labeling is not None and hasattr(labeling, "settings") else None
    return settings is None or (settings.placement == Qgis.LabelPlacement.OverPoint and settings.geometryGeneratorEnabled
                                and "label_x" in settings.geometryGenerator)


def has_labels_per_part(layer: QgsVectorLayer, table: str) -> bool:
    """Om en yta eller linje i flera delar får text på varje del (ett projekt som sparats av en äldre version skrev bara
    texten på en av delarna)."""
    if table not in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
        return True
    labeling = layer.labeling()
    settings = labeling.settings() if labeling is not None and hasattr(labeling, "settings") else None
    if settings is None:
        return True
    return settings.labelPerPart if table == "egenskap_linje" else _PARTS in settings.geometryGenerator


def has_fragile_dashes(renderer) -> bool:
    """Om en renderare har streckade linjer som passas in mot linjens längd eller har luckor på noll längd (se ``_tidy``):
    projekt sparade av en äldre version, som ger en PDF med vektorutskrift som Acrobat inte kan spara som bild."""
    def fragile(symbol) -> bool:
        for layer in symbol.symbolLayers():
            if isinstance(layer, QgsSimpleLineSymbolLayer) and layer.useCustomDashPattern():
                gaps = list(layer.customDashVector())[1::2]
                if layer.alignDashPattern() or layer.tweakDashPatternOnCorners() or any(g < MIN_DASH_GAP for g in gaps):
                    return True
            inner = layer.subSymbol() if hasattr(layer, "subSymbol") else None
            if inner is not None and fragile(inner):
                return True
        return False

    return renderer is not None and any(fragile(symbol) for symbol in renderer.symbols(QgsRenderContext()))


def has_slope_arrow(layer: QgsVectorLayer, table: str) -> bool:
    """Om egenskapsytornas renderare ritar lutningspilen (ett projekt som sparats av en äldre version ritade ingen pil för
    största och minsta lutning; se ``_slope_arrow_layer``)."""
    renderer = layer.renderer() if table == "egenskap_yta" else None
    if renderer is None:
        return True
    return any(isinstance(symbol_layer, QgsGeometryGeneratorSymbolLayer) and SLOPE_SYMBOL in symbol_layer.geometryExpression()
               for symbol in renderer.symbols(QgsRenderContext()) for symbol_layer in symbol.symbolLayers())


def has_current_symbol_class(layer: QgsVectorLayer, table: str) -> bool:
    """Om egenskapslagrets renderare klassar objekten på alla deras symboler (ett projekt som sparats med en äldre version
    klassade på ett enda värde, så en yta med både fastighetsindelning och korsmark visade bara den ena)."""
    renderer = layer.renderer()
    expected = {"egenskap_yta": _AREA_CLASS, "egenskap_linje": _LINE_CLASS}.get(table)
    return not isinstance(renderer, QgsCategorizedSymbolRenderer) or expected is None         or renderer.classAttribute() == expected


def has_outlines_last(renderer) -> bool:
    """Om en yterenderare ritar kantlinjerna sist (se ``_outlines_last``); linjelager har inget att ordna."""
    return renderer is None or not any(s.type() == Qgis.SymbolType.Fill for s in renderer.symbols(QgsRenderContext())) \
        or renderer.usingSymbolLevels()


def _set_renderer(layer: QgsVectorLayer, renderer, reference_scale: float) -> None:
    """Sätter renderaren med en fast referensskala: linjebredder och symbolstorlekar (mm) gäller vid den skalan."""
    if reference_scale:
        renderer.setReferenceScale(reference_scale)
    _outlines_last(renderer)
    layer.setRenderer(renderer)


# -- lager ------------------------------------------------------------------------------
def style_plan_area(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                    reference_scale: float = 1000) -> None:
    """Planområdet: ingen fyllning, bara planområdesgränsen (överst i hierarkin, ritas hel)."""
    _set_renderer(layer, QgsSingleSymbolRenderer(_fill(None, _outline_from(style, "Planområdesgräns"))), reference_scale)


def style_plan_area_solid(layer: QgsVectorLayer, style: QgsStyle | None = None, reference_scale: float = 1000) -> None:
    """Planområdesgränsen som en heldragen linje, för planmosaiken. Samma bredd, färg och referensskala som planens egen
    gräns, så att den håller proportion mot användningsgränsen vid alla skalor. Planerna ligger intill varandra och delar
    gräns: den streckprickade gränsen ritas då ovanpå varandra med olika fas och blir oläslig."""
    outline = _outline_from(style or load_style(), "Planområdesgräns")
    if isinstance(outline, QgsSimpleLineSymbolLayer):
        outline.setUseCustomDashPattern(False)
        outline.setPenStyle(Qt.PenStyle.SolidLine)
    _set_renderer(layer, QgsSingleSymbolRenderer(_fill(None, outline)), reference_scale)


def style_use(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
              reference_scale: float = 1000) -> None:
    expression = hierarchical_boundary(layers, "anvandning_yta", ("detaljplan",))
    _style_use(layer, reference_scale, lambda: _generated_outline(style, "Användningsgräns", expression))


def style_use_overview(layer: QgsVectorLayer, style: QgsStyle, reference_scale: float = 1000) -> None:
    """Användningsytor för översiktsskalor (planmosaiken utzoomad): samma fyllning, men kanten är en vanlig heldragen linje
    i symbolen i stället för den beräknade kanten (geometrigenerator med gränshierarki). Hierarkin döljer kanter som redan
    ritas, för att streckmönster inte ska hamna ovanpå varandra; heldragna linjer som ligger på varandra syns inte som
    dubbla, så den behövs inte här. Att rita ytans egen kant är mycket billigare."""
    def outline():
        line = _outline_from(style, "Användningsgräns")
        if isinstance(line, QgsSimpleLineSymbolLayer):
            line.setUseCustomDashPattern(False)
            line.setPenStyle(Qt.PenStyle.SolidLine)
        return line

    _style_use(layer, reference_scale, outline)


def _style_use(layer: QgsVectorLayer, reference_scale: float, outline) -> None:
    def lead(symbol):
        return _with_leader(symbol, reference_scale, USE_TEXT_MM)

    categories = [QgsRendererCategory(name, lead(_fill(rgb, outline())), name) for name, rgb in FARGER.items()]
    categories.append(QgsRendererCategory(UNASSIGNED, lead(_hatched(UNASSIGNED_COLOR, (250, 250, 250), outline())),
                                          "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", lead(_fill(FALLBACK_FARG, outline())), "Övriga"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_USE_CLASS, categories), reference_scale)
    layer.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)  # grundkartan syns genom användningens färg
    _apply_labels(layer, reference_scale, is_use=True)


def _for_kind(expression: str, secondary: bool) -> str:
    """Kantlinjen bara för egenskapsytor av rätt slag (vanlig eller sekundär egenskapsgräns), annars ingen linje. En yta
    med indelning i fastigheter har den kantlinjen i stället (se ``_for_division``)."""
    return (f"CASE WHEN coalesce(\"sekundar\", 0) = {1 if secondary else 0} AND NOT ({_DIVISION}) "
            f"THEN {expression} ELSE {_EMPTY} END")


def _for_division(expression: str) -> str:
    """Kantlinjen för indelning i fastigheter, bara för ytor som har den bestämmelsen (vid sidan av eventuell fyllning)."""
    return f"CASE WHEN {_DIVISION} THEN {expression} ELSE {_EMPTY} END"


def style_property_area(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                        reference_scale: float = 1000) -> None:
    """Egenskapsytor: vanlig egenskapsgräns (streck, punkt, punkt) eller, för ytor som ritats som sekundära, sekundär
    egenskapsgräns (streck och plustecken). Där de sammanfaller ritas de ovanpå varandra. En yta med indelning i
    fastigheter ritas med den kantlinjen i stället för egenskapsgränsen, och den kan också ha en fyllning (korsmark)."""
    expression = hierarchical_boundary(layers, "egenskap_yta", ("detaljplan", "anvandning_yta"), same_kind=True)

    def outline():
        return [_generated_outline(style, "Egenskapsgräns", _for_kind(expression, False)),
                _generated_outline(style, "Sekundär egenskapsgräns", _for_kind(expression, True)),
                *(_generated_outline(style, name, _for_division(expression)) for name in OUTLINE_SYMBOLS),
                _leader_layer(reference_scale, PROPERTY_TEXT_MM),
                _slope_arrow_layer(reference_scale, PROPERTY_TEXT_MM)]

    categories = []
    for name in AREA_SYMBOLS:
        pattern = _symbol(style, name)
        if pattern is not None:
            symbol = _robust_pattern(pattern.clone())
            _append_outlines(symbol, outline())
            categories.append(QgsRendererCategory(name, _tidy(symbol), name))
    categories.append(QgsRendererCategory(UNASSIGNED, _hatched(UNASSIGNED_COLOR, None, outline()), "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", _fill(None, outline()), "Övriga egenskaper"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_AREA_CLASS, categories), reference_scale)
    _apply_labels(layer, reference_scale, bold=False)


def style_property_line(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                        reference_scale: float = 1000) -> None:
    categories = []
    for name in LINE_SYMBOLS:
        symbol = _symbol(style, name)
        if symbol is not None:
            categories.append(QgsRendererCategory(name, _tidy(symbol.clone()), name))
    categories.append(QgsRendererCategory(UNASSIGNED, _tidy(QgsLineSymbol.createSimple(
        {"color": "220,90,40", "width": "0.6", "line_style": "dash"})), "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", _tidy(QgsLineSymbol.createSimple({"color": "0,0,0", "width": "0.5"})),
                                          "Övriga"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_LINE_CLASS, categories), reference_scale)
    _apply_labels(layer, reference_scale, bold=False, is_line=True)


def style_property_point(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                         reference_scale: float = 1000) -> None:
    """Egenskapspunkter: bara beteckningen intill punkten, för markens höjd höjden ("+31,8"), utan prick. Texten kan inte
    flyttas (ingen ledlinje). Punkter som saknar bestämmelse ritas som ett orange kryss."""
    def dot():
        # Ingen prick: texten står alltid intill punkten och kan inte flyttas, så varken punkt eller ledlinje behövs.
        symbol = _tidy(QgsMarkerSymbol.createSimple({"name": "circle", "color": "0,0,0", "outline_style": "no",
                                                     "size": str(POINT_MARKER_MM)}))
        symbol.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.Property.LayerEnabled,
                                                     QgsProperty.fromExpression('is_selected()'))
        return symbol

    categories = [QgsRendererCategory(UNASSIGNED, _tidy(QgsMarkerSymbol.createSimple(
        {"name": "cross", "color": "220,90,40", "outline_color": "220,90,40", "outline_width": "0.5", "size": "2.6"})),
        "Saknar bestämmelse"), QgsRendererCategory("", dot(), "Egenskapspunkt")]
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_UNASSIGNED_CLASS, categories), reference_scale)
    _apply_labels(layer, reference_scale, bold=False, is_point=True)


def style_helper_line(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                      reference_scale: float = 1000) -> None:
    """Hjälplinjer: tunn, heldragen, svagt genomskinlig cyan linje som tydligt skiljer sig från plangeometrin."""
    symbol = _tidy(QgsLineSymbol.createSimple({"color": "0,255,255", "width": "0.3"}))
    symbol.setOpacity(0.7)
    _set_renderer(layer, QgsSingleSymbolRenderer(symbol), reference_scale)
    layer.setLabelsEnabled(False)


def style_helper_area(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                      reference_scale: float = 1000) -> None:
    """Hjälpytor: som hjälplinjerna, en tunn cyan kant, med en mycket svag fyllning så att ytan syns men inte döljer
    planen under."""
    symbol = _tidy(QgsFillSymbol.createSimple({"color": "0,255,255,28", "outline_color": "0,255,255",
                                               "outline_width": "0.3", "style": "solid"}))
    symbol.setOpacity(0.85)
    _set_renderer(layer, QgsSingleSymbolRenderer(symbol), reference_scale)
    layer.setLabelsEnabled(False)


def style_helper_point(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                       reference_scale: float = 1000) -> None:
    """Hjälppunkter: ett litet cyan kors."""
    symbol = _tidy(QgsMarkerSymbol.createSimple({"name": "cross", "color": "0,255,255", "outline_color": "0,255,255",
                                                 "outline_width": "0.4", "size": "2.6"}))
    _set_renderer(layer, QgsSingleSymbolRenderer(symbol), reference_scale)
    layer.setLabelsEnabled(False)


_STYLERS = {
    "hjalplinje": style_helper_line,
    "hjalpyta": style_helper_area,
    "hjalppunkt": style_helper_point,
    "detaljplan": style_plan_area,
    "anvandning_yta": style_use,
    "egenskap_yta": style_property_area,
    "egenskap_linje": style_property_line,
    "egenskap_punkt": style_property_point,
}


def has_current_colours(layer: QgsVectorLayer) -> bool:
    """Om användningsytornas färger är dem i ``FARGER`` (ett projekt som sparats med äldre färger har andra)."""
    renderer = layer.renderer()
    if not isinstance(renderer, QgsCategorizedSymbolRenderer):
        return True
    for category in renderer.categories():  # kopior: hålls kvar medan symbolen läses
        expected = FARGER.get(category.value())
        symbol = category.symbol()
        if expected is None or symbol is None or not symbol.symbolLayerCount():
            continue
        colour = symbol.symbolLayer(0).color()
        if (colour.red(), colour.green(), colour.blue()) != expected:
            return False
    return True


def draw_unassigned_as_others(layer: QgsVectorLayer) -> None:
    """Ritar objekt som saknar bestämmelse som övriga objekt (ingen röd skraffering, streckad linje eller kryss). I en
    plan visar markeringen vad som återstår att göra; i planmosaiken tittar man bara på planerna."""
    renderer = layer.renderer()
    if not isinstance(renderer, QgsCategorizedSymbolRenderer):
        return
    categories = renderer.categories()  # kopior: hålls kvar medan symbolen klonas
    default = next((c for c in categories if c.value() == ""), None)
    unassigned = next((i for i, c in enumerate(categories) if c.value() == UNASSIGNED), None)
    if default is None or unassigned is None:
        return
    symbol = default.symbol().clone()
    renderer.updateCategorySymbol(unassigned, symbol)
    renderer.updateCategoryLabel(unassigned, default.label())


def apply_symbology(layers: dict[str, QgsVectorLayer], style: QgsStyle | None = None,
                    reference_scale: float = 1000) -> None:
    """Sätter symbologi och etiketter på planens lager (tabellnamn -> lager)."""
    style = style or load_style()
    for table, styler in _STYLERS.items():
        if table in layers:
            styler(layers[table], style, layers, reference_scale)
