"""Förhandsvisning av topologikontrollens förslag i kartan: en röd ring där en brytpunkt ligger nu, en grön där den
hamnar och en linje mellan dem. En brytpunkt som läggs till visas bara som grön, en som tas bort bara som röd. Ringarna har
fast storlek i bildpunkter, så att en ändring på någon millimeter syns lika tydligt som en på en decimeter."""
from __future__ import annotations

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtGui import QColor

from ..core.topology import Change

RED, GREEN = QColor(179, 38, 30), QColor(27, 127, 59)
ICON_SIZE = 14  # bildpunkter


class TopologyPreview:
    """``show(ändringar)`` ritar förhandsvisningen (ersätter den förra), ``clear()`` tar bort den. ``show([])`` rensar
    också, så att den går att skicka direkt till dialogen som återanrop."""

    def __init__(self, canvas: QgsMapCanvas):
        self._canvas = canvas
        self._lines = self._band(Qgis.GeometryType.Line, RED)
        self._old = self._band(Qgis.GeometryType.Point, RED, QgsRubberBand.IconType.ICON_CIRCLE)
        self._new = self._band(Qgis.GeometryType.Point, GREEN, QgsRubberBand.IconType.ICON_CIRCLE)

    def _band(self, kind, color: QColor, icon=None) -> QgsRubberBand:
        band = QgsRubberBand(self._canvas, kind)
        band.setColor(color)
        band.setStrokeColor(color)
        band.setFillColor(QColor(0, 0, 0, 0))
        band.setWidth(2)
        if icon is not None:
            band.setIcon(icon)
            band.setIconSize(ICON_SIZE)
        return band

    def show(self, changes: list[Change]) -> None:
        self.clear()
        old_points = [QgsPointXY(*c.old) for c in changes if c.old is not None]
        new_points = [QgsPointXY(*c.new) for c in changes if c.new is not None]
        moves = [[QgsPointXY(*c.old), QgsPointXY(*c.new)] for c in changes if c.old is not None and c.new is not None]
        if old_points:
            self._old.setToGeometry(QgsGeometry.fromMultiPointXY(old_points), None)
        if new_points:
            self._new.setToGeometry(QgsGeometry.fromMultiPointXY(new_points), None)
        if moves:
            self._lines.setToGeometry(QgsGeometry.fromMultiPolylineXY(moves), None)

    def clear(self) -> None:
        self._lines.reset(Qgis.GeometryType.Line)
        self._old.reset(Qgis.GeometryType.Point)
        self._new.reset(Qgis.GeometryType.Point)

    def is_empty(self) -> bool:
        """Visas ingenting just nu."""
        return all(band.asGeometry() is None or band.asGeometry().isEmpty()
                   for band in (self._lines, self._old, self._new))
