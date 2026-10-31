"""Exportera plankartans layout som PDF med de inställningar som ger en PDF som går att arkivera, och kontrollera den.

En knapp i layoutläget gör allt: exporterar som **vektorgrafik** (kartan blir ingen bild), utan georeferens (den ger
anmärkningar i en PDF/A-kontroll och behövs inte för en plankarta), och kontrollerar sedan filen (``pdfcheck``).
"""
from __future__ import annotations

from pathlib import Path

from qgis.core import QgsLayoutExporter, QgsLayoutItemMap, QgsProject
from qgis.PyQt.QtGui import QPainter

from . import pdfcheck


class ExportError(RuntimeError):
    """Exporten misslyckades. Meddelandet är avsett för användaren."""


def map_layers(layout) -> list:
    """Lagren som layoutens kartor ritar: kartans egna om de är låsta, annars projektets synliga lager."""
    project = layout.project() or QgsProject.instance()
    layers = []
    for item in layout.items():
        if isinstance(item, QgsLayoutItemMap):
            own = item.layers()
            layers += own if own else project.layerTreeRoot().checkedLayers()
    return layers


def blend_mode_layers(layout) -> list:
    """Kartans lager med ett blandningsläge (till exempel Multiplicera): de finns inte i en PDF med vektorutskrift."""
    normal = QPainter.CompositionMode.CompositionMode_SourceOver
    return [layer for layer in map_layers(layout)
            if layer.blendMode() != normal or layer.featureBlendMode() != normal]


def export_pdf(layout, path, vector: bool = True) -> pdfcheck.PdfReport:
    """Exporterar ``layout`` som PDF till ``path`` och returnerar kontrollen av filen."""
    path = Path(path)
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.forceVectorOutput = vector
    settings.appendGeoreference = False
    result = QgsLayoutExporter(layout).exportToPdf(str(path), settings)
    if result != QgsLayoutExporter.ExportResult.Success:
        reasons = {QgsLayoutExporter.ExportResult.FileError: "Filen kunde inte skrivas (är den öppen i ett annat program?).",
                   QgsLayoutExporter.ExportResult.PrintError: "Utskriften misslyckades.",
                   QgsLayoutExporter.ExportResult.MemoryError: "Det tog slut på minne: prova en lägre upplösning."}
        raise ExportError(reasons.get(result, "Exporten misslyckades.") + f" ({path})")
    report = pdfcheck.check_pdf(path)
    if vector:
        names = sorted({layer.name() for layer in blend_mode_layers(layout)})
        if names:
            report.findings.insert(0, pdfcheck.Finding(
                pdfcheck.INFO, "I en PDF med vektorutskrift finns inga blandningslägen: " + ", ".join(names) + " ritas "
                "därför utan Multiplicera, så att färgen täcker det som ligger under (till exempel grundkartan). Lägg "
                "grundkartan överst om den ska synas genom planens färger."))
    return report
