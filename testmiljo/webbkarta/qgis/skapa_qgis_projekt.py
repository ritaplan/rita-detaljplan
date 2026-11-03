"""Skapar QGIS-projektet som QGIS Server publicerar: planmosaiken ritad som en plankarta med pluginets egen symbologi.

Lagren är publiceringsvyerna (anvandning, egenskap, gränslinjer) i en grupp, planmosaik_karta, som WMS ritar som ett enda
lager. Färger, mönster och streckmönster kommer ur pluginets stilbibliotek (Boverkets symboler, BFS 2020:6), så kartan
ser likadan ut som i Rita Detaljplan. Projektet anger bara vyerna och en tjänstedefinition: lösenordet står aldrig i det.

Behöver två filer ur pluginet i samma mapp som det här skriptet (kopiera dem, de är inte med i den här mappen):
    rita_detaljplan/core/symbology.py
    rita_detaljplan/data/styles/detaljplaner-bfs-2020-6.xml

Körs med QGIS egen Python, helst i samma avbildning som QGIS Server (så att databasen nås på samma sätt):

    docker run --rm --network postgis_default -v "$PWD/qgis:/io/data" \\
        -v "$PWD/qgis/pg_service.conf:/etc/postgresql-common/pg_service.conf:ro" \\
        -e QT_QPA_PLATFORM=offscreen -e PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages \\
        qgis/qgis-server:4.2.3-resolute python3 /io/data/skapa_qgis_projekt.py [epsg]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qgis.core import (QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,  # noqa: E402
                       QgsFeatureRequest, QgsFillSymbol, QgsProject, QgsProperty, QgsRendererCategory,
                       QgsSimpleFillSymbolLayer, QgsSingleSymbolRenderer, QgsSymbolLayer, QgsVectorLayer)
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtGui import QColor  # noqa: E402
from symbology import _robust_pattern, _symbol, _tidy, load_style  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "planmosaik.qgs"
EPSG = int(sys.argv[1]) if len(sys.argv) > 1 else 3008
GROUP = "planmosaik_karta"
FILL_OPACITY = 0.75  # användningens färg ligger över grundkartan (pluginet multiplicerar den; ett WMS-lager kan inte det)

app = QgsApplication([], False)
app.initQgis()
style = load_style(HERE / "detaljplaner-bfs-2020-6.xml")


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


def property_renderer() -> QgsCategorizedSymbolRenderer:
    """Egenskapsytor: mönstret ur stilbiblioteket (prickmark, korsmark, ringprickad mark)."""
    names = {"prickmark": "Marken får inte förses med byggnad/byggnadsverk",
             "korsmark": "Marken får endast förses med viss typ av byggnadsverk",
             "ringprickad": "Marken får endast förses med byggnadsverk under mark"}
    categories = []
    for value, name in names.items():
        symbol = _symbol(style, name)
        if symbol is not None:
            categories.append(QgsRendererCategory(value, _tidy(_robust_pattern(symbol.clone())), name))
    return QgsCategorizedSymbolRenderer("monster", categories)


def boundary_renderer() -> QgsCategorizedSymbolRenderer:
    """Gränslinjer med Boverkets streckmönster. Den högsta gränsen ritas sist, så att den hamnar överst."""
    categories = []
    for value, name in (("egenskapsgrans", "Egenskapsgräns"), ("anvandningsgrans", "Användningsgräns"),
                        ("planomradesgrans", "Planområdesgräns")):
        categories.append(QgsRendererCategory(value, _tidy(style.symbol(name).clone()), name))
    renderer = QgsCategorizedSymbolRenderer("typ", categories)
    order = ("CASE \"typ\" WHEN 'planomradesgrans' THEN 3 WHEN 'anvandningsgrans' THEN 2 ELSE 1 END")
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
