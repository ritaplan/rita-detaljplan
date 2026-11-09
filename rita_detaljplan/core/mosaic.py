"""Planmosaik: alla planer i ett schema som ett enda skrivskyddat lagerset i QGIS.

En plan läses vanligtvis med ett filter på planens id. Mosaiken läser samma tabeller utan det filtret, men bara de planer
vars status användaren valt. Den är bara en vy, utan etiketter och utan markering av det som saknar bestämmelse: lagren märks inte som en plan (se ``project.PLAN_GROUP_PROPERTY``), så
pluginets verktyg, aktiv plan och utcheckning ser dem aldrig, och ingenting går att redigera.
"""
from __future__ import annotations

from dataclasses import dataclass

from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer

from . import model, settings, storage, symbology
from .storage import literal, quote

MOSAIC_GROUP_PROPERTY = "detaljplan_ngp/mosaic_group"  # markerar gruppen som håller en planmosaik
MOSAIC_CONNECTION_PROPERTY = "detaljplan_ngp/mosaic_connection"
MOSAIC_SCHEMA_PROPERTY = "detaljplan_ngp/mosaic_schema"

# Lagren i samma ordning som i en plan (överst först), utan tabeller och hjälplager.
MOSAIC_LAYERS = (model.EGENSKAP_PUNKT, model.EGENSKAP_LINJE, model.DETALJPLAN, model.EGENSKAP_YTA, model.ANVANDNING_YTA)
DEFAULT_STATUSES = ("antagen", "laga kraft")
NO_STATUS = ""  # planer som saknar status
DETAIL_SCALE = 200_000  # användning och egenskaper ritas inte i en mindre skala än 1:200 000 (planområdena alltid)


@dataclass(frozen=True)
class Mosaic:
    group: object  # lagerträdets grupp
    layers: dict[str, QgsVectorLayer]


def status_label(status: str) -> str:
    return status or "utan status"


def status_condition(statuses) -> str:
    """SQL-villkoret för planernas status. Tom text i ``statuses`` betyder planer som saknar status."""
    wanted = [s for s in statuses if s != NO_STATUS]
    parts = []
    if wanted:
        parts.append(f'"status" IN ({", ".join(literal(s) for s in wanted)})')
    if NO_STATUS in statuses:
        parts.append('"status" IS NULL OR "status" = \'\'')
    if not parts:
        raise ValueError("Välj minst en planstatus.")
    return "(" + " OR ".join(parts) + ")"


def subset(layer_def: model.LayerDef, schema: str, statuses) -> str:
    """Urvalet för ett lager: planområdet har statusen själv, de andra lagren hämtar den från sin plans planområde."""
    condition = status_condition(statuses)
    if layer_def is model.DETALJPLAN:
        return condition
    return f'"plan" IN (SELECT "plan" FROM {quote(schema)}.{quote(model.DETALJPLAN.name)} WHERE {condition})'


def mosaic_groups(project: QgsProject) -> list:
    return [g for g in project.layerTreeRoot().findGroups() if g.customProperty(MOSAIC_GROUP_PROPERTY)]


def remove_mosaic(project: QgsProject, connection_name: str, schema: str) -> None:
    """Tar bort en tidigare mosaik för samma schema (lagren och gruppen), så att en ny kan ersätta den."""
    for group in mosaic_groups(project):
        if (group.customProperty(MOSAIC_CONNECTION_PROPERTY), group.customProperty(MOSAIC_SCHEMA_PROPERTY)) == \
                (connection_name, schema):
            ids = [node.layerId() for node in group.findLayers()]
            project.layerTreeRoot().removeChildNode(group)
            project.removeMapLayers(ids)


def load_mosaic(project: QgsProject, connection_name: str, schema: str, statuses, connection=None) -> Mosaic:
    """Lägger planmosaiken för ``schema`` i ``project``: en grupp med planernas lager, skrivskyddade och med planens
    utseende. Ersätter en tidigare mosaik för samma schema. Kastar ``ValueError`` om schemat inte går att läsa."""
    statuses = tuple(statuses)
    status_condition(statuses)  # tomt val avvisas innan något läses
    source = storage.PostgisStorage(connection_name, schema, "", connection)
    meta = source.read_schema_meta()
    if not meta:
        raise ValueError(f"{schema} är inte ett schema skapat av detta plugin")
    if meta.get("schema_version") != str(model.SCHEMA_VERSION):
        raise ValueError(f"Schemat {schema} har schemaversion {meta.get('schema_version')}, nu krävs {model.SCHEMA_VERSION}. "
                         "Öppna en plan i schemat först: då uppgraderas schemat.")
    remove_mosaic(project, connection_name, schema)
    layers: dict[str, QgsVectorLayer] = {}
    for layer_def in MOSAIC_LAYERS:
        layer = source.make_layer(layer_def, subset(layer_def, schema, statuses))
        if not layer.isValid():
            raise ValueError(f"Kunde inte läsa tabellen {layer_def.name} i schemat {schema}")
        layer.setReadOnly(True)
        if layer_def is not model.DETALJPLAN:
            layer.setScaleBasedVisibility(True)
            layer.setMinimumScale(DETAIL_SCALE)
        layers[layer_def.name] = layer
    project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{meta['epsg']}"))
    group = project.layerTreeRoot().insertGroup(0, f"Planmosaik {schema}: " + ", ".join(status_label(s) for s in statuses))
    group.setCustomProperty(MOSAIC_GROUP_PROPERTY, "1")
    group.setCustomProperty(MOSAIC_CONNECTION_PROPERTY, connection_name)
    group.setCustomProperty(MOSAIC_SCHEMA_PROPERTY, schema)
    for layer_def in MOSAIC_LAYERS:
        project.addMapLayer(layers[layer_def.name], False)
        group.addLayer(layers[layer_def.name])
    symbology.apply_symbology(layers, reference_scale=settings.reference_scale())
    for layer in layers.values():
        layer.setLabelsEnabled(False)  # bestämmelsernas texter behövs inte i en översikt, och hundratals planer blir tungt
        symbology.draw_unassigned_as_others(layer)  # inget rött för det som saknar bestämmelse
    # grannplaner delar gräns: heldragen i stället för streckprickad
    symbology.style_plan_area_solid(layers[model.DETALJPLAN.name], reference_scale=settings.reference_scale())
    return Mosaic(group, layers)


def full_extent(mosaic: Mosaic):
    """Planområdenas utsträckning (eller None om inga planer valts ut), för att zooma kartan dit."""
    extent = mosaic.layers[model.DETALJPLAN.name].extent()
    return None if extent.isEmpty() or extent.isNull() else extent
