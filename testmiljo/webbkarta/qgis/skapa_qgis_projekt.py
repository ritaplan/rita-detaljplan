"""Skapar QGIS-projektet som QGIS Server publicerar: planmosaik-vyn med stil och WMS/WFS påslaget.

Körs med QGIS egen Python, helst i samma avbildning som QGIS Server (så att databasen nås på samma sätt):

    docker run --rm --network postgis_default -v "$PWD/qgis:/io/data" \\
        -v "$PWD/qgis/pg_service.conf:/etc/postgresql-common/pg_service.conf:ro" \\
        -e QT_QPA_PLATFORM=offscreen -e PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages \\
        qgis/qgis-server:4.2.3-resolute python3 /io/data/skapa_qgis_projekt.py

Databasuppgifterna (inklusive lösenordet) ligger i pg_service.conf och hamnar aldrig i projektfilen.
"""
from qgis.core import (QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsFillSymbol,
                       QgsPalLayerSettings, QgsProject, QgsRendererCategory, QgsTextFormat, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)

OUT = "/io/data/planmosaik.qgs"
SOURCE = ("service='planmosaik' sslmode=require key='fid' srid=3008 type=MultiPolygon "
          "table=\"publicering\".\"planmosaik\" (geom)")
# Samma färger i alla tre kartsätten (GeoServer-stilen, QGIS och Origo/Martin)
CATEGORIES = (
    ("gällande, genomförandetiden pågår", "#3b9b6a"),
    ("gällande, genomförandetiden har gått ut", "#8a94a0"),
    ("gällande", "#4a7fc1"),
    ("antagen", "#e0a030"),
)

app = QgsApplication([], False)
app.initQgis()

layer = QgsVectorLayer(SOURCE, "planmosaik", "postgres")
if not layer.isValid():
    raise SystemExit(f"Lagret kunde inte läsas: {layer.error().summary()}")
categories = []
for value, color in CATEGORIES:
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    # QGIS läser #AARRGGBB, inte #RRGGBBAA: skriv fyllnadsfärgen med genomskinlighet som r,g,b,a
    symbol = QgsFillSymbol.createSimple({"color": f"{red},{green},{blue},153", "outline_color": color,
                                         "outline_width": "0.5"})
    categories.append(QgsRendererCategory(value, symbol, value))
layer.setRenderer(QgsCategorizedSymbolRenderer("visningsstatus", categories))

labels = QgsPalLayerSettings()
labels.fieldName = "beteckning"
labels.placement = QgsPalLayerSettings.Placement.OverPoint
text = QgsTextFormat()
text.setSize(9)
labels.setFormat(text)
layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
layer.setLabelsEnabled(True)

project = QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3008"))
project.addMapLayer(layer)
project.setTitle("Planmosaik")

# Det här är vad "OWS-inställningarna" i QGIS projektegenskaper sparar.
project.writeEntry("WMSServiceCapabilities", "/", True)
project.writeEntry("WMSServiceTitle", "/", "Planmosaik")
project.writeEntry("WMSServiceAbstract", "/", "Detaljplaner som är antagna eller har vunnit laga kraft")
project.writeEntry("WMSCrsList", "/", ["EPSG:3008", "EPSG:3006", "EPSG:3857", "EPSG:4326"])
project.writeEntry("WMSUseLayerIDs", "/", False)
project.writeEntry("WFSLayers", "/", [layer.id()])
project.writeEntry("WFSLayersPrecision", f"/{layer.id()}", 3)

if not project.write(OUT):
    raise SystemExit("Projektet kunde inte sparas")
print(f"Sparade {OUT}: {layer.featureCount()} planer, utbredning {layer.extent().toString(0)}")
app.exitQgis()
