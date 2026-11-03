"""Skapar QGIS-projektet som QGIS Server publicerar: planmosaiken ritad som en plankarta.

Lagren är publiceringsvyerna (användning, egenskap, gränslinjer) i en grupp, planmosaik_karta, som WMS ritar som ett enda
lager. Färger, mönster och streckmönster är Boverkets (BFS 2020:6), som i Rita Detaljplan. Mått i pixlar skalas med
kartskalan i band, enligt stil.py: linjer och mönster blir mindre när man zoomar ut och försvinner när de blivit för små.
Projektet anger bara vyerna och en tjänstedefinition: lösenordet står aldrig i det.

Behöver stil.py (i mappen ovanför, eller kopierad hit) i samma mapp som skriptet när det körs i en behållare.

Körs med QGIS egen Python, helst i samma avbildning som QGIS Server (så att databasen nås på samma sätt):

    docker run --rm --network postgis_default -v "$PWD/qgis:/io/data" \\
        -v "$PWD/qgis/pg_service.conf:/etc/postgresql-common/pg_service.conf:ro" \\
        -e QT_QPA_PLATFORM=offscreen -e PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages \\
        qgis/qgis-server:4.2.3-resolute python3 /io/data/skapa_qgis_projekt.py [epsg]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import stil  # noqa: E402
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsFeatureRequest,  # noqa: E402
                       QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol, QgsPointPatternFillSymbolLayer, QgsProject,
                       QgsProperty, QgsRuleBasedRenderer, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer,
                       QgsSimpleMarkerSymbolLayer, QgsSingleSymbolRenderer, QgsSymbolLayer, QgsVectorLayer)
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtGui import QColor  # noqa: E402

OUT = HERE / "planmosaik.qgs"
EPSG = int(sys.argv[1]) if len(sys.argv) > 1 else 3008
GROUP = "planmosaik_karta"
FILL_OPACITY = 0.75  # användningens färg ligger över grundkartan (pluginet multiplicerar den; ett WMS-lager kan inte det)

app = QgsApplication([], False)
app.initQgis()


def layer_from_view(name: str, title: str, geometry: str) -> QgsVectorLayer:
    source = (f"service='planmosaik' sslmode=require key='fid' srid={EPSG} type={geometry} "
              f"table=\"publicering\".\"{name}\" (geom)")
    layer = QgsVectorLayer(source, name, "postgres")
    if not layer.isValid():
        raise SystemExit(f"Lagret {name} kunde inte läsas: {layer.error().summary()}")
    layer.serverProperties().setTitle(title)  # namnet i WMS är vyns namn (LAYERS=plan_anvandning), titeln visas i listor
    return layer


def use_renderer() -> QgsSingleSymbolRenderer:
    """Användningsytor: fyllning i Boverkets färg (fältet fyllfarg), ingen kantlinje (gränserna är ett eget lager)."""
    fill = QgsSimpleFillSymbolLayer(QColor(245, 245, 245))
    fill.setStrokeStyle(Qt.PenStyle.NoPen)
    fill.setDataDefinedProperty(QgsSymbolLayer.Property.FillColor, QgsProperty.fromField("fyllfarg"))
    symbol = QgsFillSymbol()
    symbol.deleteSymbolLayer(0)
    symbol.appendSymbolLayer(fill)
    symbol.setOpacity(FILL_OPACITY)
    return QgsSingleSymbolRenderer(symbol)


PIXELS = Qgis.RenderUnit.Pixels
BLACK = QColor(0, 0, 0)


def _scale_rules(root, symbols_by_band, label: str, expression: str):
    """Lägger en regel per skalband. ``symbols_by_band`` är (från, till, symbol) och hoppar över band utan symbol."""
    for lower, upper, symbol in symbols_by_band:
        if symbol is None:
            continue
        # QGIS: "maximumScale" är den lägre och "minimumScale" den högre nämnaren (0 = obegränsat)
        rule = QgsRuleBasedRenderer.Rule(symbol, lower, upper or 0, expression, f"{label} {lower}-{upper or ''}")
        root.appendChild(rule)


def _or_none(make_symbol, style):
    """Symbolen för ett band, eller None om stilen för bandet är None (ritas inte)."""
    return make_symbol(style) if style else None


def _line_symbol(style: dict) -> QgsLineSymbol:
    layer = QgsSimpleLineSymbolLayer(BLACK, style["width"])
    layer.setWidthUnit(PIXELS)
    layer.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    layer.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if style["dash"]:
        layer.setUseCustomDashPattern(True)
        layer.setCustomDashPatternUnit(PIXELS)
        layer.setCustomDashVector(style["dash"])
        layer.setAlignDashPattern(False)
        layer.setTweakDashPatternOnCorners(False)
    symbol = QgsLineSymbol()
    symbol.deleteSymbolLayer(0)
    symbol.appendSymbolLayer(layer)
    symbol.setClipFeaturesToExtent(False)
    return symbol


def _pattern_symbol(style: dict) -> QgsFillSymbol:
    """Prickar, kors eller ringar i förskjutna rader, som i pluginet."""
    shape = {"circle": Qgis.MarkerShape.Circle, "ring": Qgis.MarkerShape.Circle, "cross": Qgis.MarkerShape.Cross}
    filled = style["shape"] == "circle"
    marker = QgsSimpleMarkerSymbolLayer(shape[style["shape"]], style["size"], 0.0, Qgis.ScaleMethod.ScaleDiameter,
                                        BLACK if filled else QColor(0, 0, 0, 0), BLACK)
    marker.setSizeUnit(PIXELS)
    marker.setStrokeWidth(0 if filled else style["stroke"])
    marker.setStrokeWidthUnit(PIXELS)
    pattern = QgsPointPatternFillSymbolLayer()
    pattern.setSubSymbol(QgsMarkerSymbol([marker]))
    pattern.setDistanceX(style["period"])
    pattern.setDistanceY(style["period"])
    pattern.setDisplacementX(style["period"] / 2)  # varannan rad förskjuten
    for set_unit in (pattern.setDistanceXUnit, pattern.setDistanceYUnit, pattern.setDisplacementXUnit):
        set_unit(PIXELS)
    pattern.setClipMode(Qgis.MarkerClipMode.CentroidWithin)
    symbol = QgsFillSymbol()
    symbol.deleteSymbolLayer(0)
    symbol.appendSymbolLayer(pattern)
    symbol.setClipFeaturesToExtent(False)
    return symbol


def property_renderer() -> QgsRuleBasedRenderer:
    """Egenskapsytor: mönster (prickmark, korsmark, ringprickad mark) som skalas med kartskalan och försvinner när de blir för små."""
    root = QgsRuleBasedRenderer.Rule(None)
    for kind in stil.PATTERNS:
        bands = [(lower, upper, _or_none(_pattern_symbol, stil.pattern_style(kind, scale)))
                 for lower, upper, scale in stil.bands()]
        _scale_rules(root, bands, kind, f"\"monster\" = '{kind}'")
    return QgsRuleBasedRenderer(root)


def boundary_renderer() -> QgsRuleBasedRenderer:
    """Gränslinjer med Boverkets streckmönster, skalade med kartskalan. Den högsta gränsen ritas sist, så att den hamnar överst."""
    root = QgsRuleBasedRenderer.Rule(None)
    for kind in stil.LINES:
        bands = [(lower, upper, _or_none(_line_symbol, stil.line_style(kind, lower, scale)))
                 for lower, upper, scale in stil.bands()]
        _scale_rules(root, bands, kind, f"\"typ\" = '{kind}'")
    renderer = QgsRuleBasedRenderer(root)
    order = "CASE \"typ\" WHEN 'planomradesgrans' THEN 3 WHEN 'anvandningsgrans' THEN 2 ELSE 1 END"
    renderer.setOrderBy(QgsFeatureRequest.OrderBy([QgsFeatureRequest.OrderByClause(order)]))
    renderer.setOrderByEnabled(True)
    return renderer


# Överst först: lagerträdet ritas nerifrån och upp, så gränserna överst hamnar ovanpå mönstren och färgen.
LAYERS = (("plan_gransar", "Gränslinjer", "MultiLineString", boundary_renderer),
          ("plan_egenskap", "Egenskapsytor", "MultiPolygon", property_renderer),
          ("plan_anvandning", "Användningsytor", "MultiPolygon", use_renderer))

project = QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{EPSG}"))
project.setTitle("Planmosaik")
group = project.layerTreeRoot().addGroup(GROUP)
ids = []
for name, title, geometry, renderer in LAYERS:
    layer = layer_from_view(name, title, geometry)
    layer.setRenderer(renderer())
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    ids.append(layer.id())
    print(f"{title}: {layer.featureCount()} objekt")

# Det här är vad "OWS-inställningarna" i QGIS projektegenskaper sparar.
project.writeEntry("WMSServiceCapabilities", "/", True)
project.writeEntry("WMSServiceTitle", "/", "Planmosaik")
project.writeEntry("WMSServiceAbstract", "/", "Detaljplaner som är antagna eller har vunnit laga kraft")
project.writeEntry("WMSCrsList", "/", [f"EPSG:{EPSG}", "EPSG:3006", "EPSG:3857", "EPSG:4326"])
project.writeEntry("WMSUseLayerIDs", "/", False)
project.writeEntry("WFSLayers", "/", ids)
for layer_id in ids:
    project.writeEntry("WFSLayersPrecision", f"/{layer_id}", 3)

if not project.write(str(OUT)):
    raise SystemExit("Projektet kunde inte sparas")
print(f"Sparade {OUT}")
app.exitQgis()
