"""Textverktyget: markera bestämmelsernas texter (klick eller rektangel), flytta dem till lämpligt ställe, forma om
textrutan och rotera texten.

  * Klick på en text markerar den (skift-klick lägger till). Dra en markerad text för att flytta den (och alla andra
    markerade texter lika långt).
  * Tryck ned musknappen på tomt ställe och dra för att markera texter med en rektangel.
  * En markerad text (användning eller egenskapsyta) har fyra handtag (hörnen): dra i ett hörn för att omforma textrutan.
    Texten radbryts då efter rutans bredd; bokstävernas storlek ändras aldrig här (den ställs in i skalningsinställningarna).
  * **Rotera:** håll musen strax utanför ett hörn på en markerad text (användning eller egenskapsyta). Markören blir en
    rotationspil. Dra för att vrida texten runt sin mitt; håll ned skift för att låsa vinkeln till steg om 15 grader. Själva
    hörnet (handtaget) omformar fortfarande rutan, också på en roterad text.
  * Delete återställer markerade texter till automatisk placering, form och vågrät vinkel. Esc avmarkerar.
Texten kan flyttas utanför sin yta: en tunn, svart ledlinje ritas då automatiskt till ytan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from qgis.core import NULL, Qgis, QgsGeometry, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ..controller import LABEL_TABLES, PlanController
from ..core.project import table_of

DRAG_PIXELS = 4  # kortare drag än så räknas som ett klick
HANDLE_PIXELS = 8  # hur nära ett hörn man ska klicka för att ta tag i det
ROTATE_PIXELS = 22  # hur långt utanför ett hörn rotationspilen visas (bildpunkter från hörnet)
SNAP_DEGREES = 15.0  # med skift nedtryckt låses vinkeln till steg om så många grader
RESIZE, ROTATE = "resize", "rotate"  # vad man tar tag i vid ett hörn


@dataclass(frozen=True)
class LabelRef:
    """En text på kartan: vilken yta den hör till och var den ritades (kartkoordinater). ``rect`` är textrutan som den
    ser ut utan rotation, runt textens mitt; ``angle`` är hur många grader moturs den är vriden (0 = vågrät)."""
    table: str
    fid: int
    rect: QgsRectangle
    angle: float = 0.0

    @property
    def key(self) -> tuple[str, int]:
        return self.table, self.fid


class LabelTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, report):
        super().__init__(canvas)
        self.controller = controller
        self.report = report
        self.selected: list[LabelRef] = []
        self._mode: Optional[str] = None  # "move" | "rect" | "resize" | "rotate"
        self._resizing: Optional[tuple[LabelRef, QgsPointXY]] = None  # (text, det motsatta hörnet som ligger fast)
        self._rotating: Optional[tuple[LabelRef, float]] = None  # (text, musens vinkel runt textens mitt när man tog tag)
        self._start: Optional[QgsPointXY] = None
        self._shift = False
        self._zone: Optional[str] = None  # vad markören står över just nu (RESIZE, ROTATE eller inget)
        self._default_cursor = QCursor(Qt.CursorShape.PointingHandCursor)
        self._rotate_cursor = _rotation_cursor()
        self.current_cursor = self._default_cursor  # den markör verktyget senast satte (QgsMapTool har ingen get-metod)
        self.setCursor(self._default_cursor)
        self._marks = self._band(QColor(30, 110, 200, 40), QColor(30, 110, 200))
        self._ghosts = self._band(QColor(30, 110, 200, 20), QColor(30, 110, 200, 160))
        self._frame = self._band(QColor(30, 110, 200, 20), QColor(30, 110, 200))
        self._handles = QgsRubberBand(self.canvas(), Qgis.GeometryType.Point)
        self._handles.setColor(QColor(30, 110, 200))
        self._handles.setIcon(QgsRubberBand.IconType.ICON_FULL_BOX)
        self._handles.setIconSize(7)

    def _band(self, fill: QColor, stroke: QColor) -> QgsRubberBand:
        band = QgsRubberBand(self.canvas(), Qgis.GeometryType.Polygon)
        band.setColor(fill)
        band.setStrokeColor(stroke)
        band.setWidth(1)
        return band

    # -- vilka texter finns (avläses ur kartans senaste ritning) -----------------------
    def _all(self, positions) -> list[LabelRef]:
        found = []
        for position in positions:
            layer = self.controller.project.mapLayer(position.layerID)
            table = table_of(layer) if layer is not None else None
            if table in LABEL_TABLES and not position.isUnplaced:
                found.append(self._ref(layer, table, position))
        return found

    @staticmethod
    def _ref(layer, table: str, position) -> LabelRef:
        """En text ur kartans ritning. En roterad text anges av QGIS med den omslutande rutan, så textrutan utan rotation
        byggs av textens mitt och dess verkliga bredd och höjd, och vinkeln läses ur ytans ``label_rot``."""
        rect = QgsRectangle(position.labelRect)
        angle = 0.0
        feature = layer.getFeature(position.featureId) if "label_rot" in layer.fields().names() else None
        stored = feature["label_rot"] if feature is not None and feature.isValid() else None
        if stored not in (None, NULL) and float(stored) != 0.0:
            angle = _visual_angle(float(stored))  # lagrad vinkel är medurs, verktyget räknar moturs
            width, height = getattr(position, "width", None), getattr(position, "height", None)
            if width and height:
                center = rect.center()
                rect = QgsRectangle(center.x() - width / 2, center.y() - height / 2,
                                    center.x() + width / 2, center.y() + height / 2)
        return LabelRef(table, position.featureId, rect, angle)

    def labels_at(self, point: QgsPointXY) -> list[LabelRef]:
        results = self.canvas().labelingResults(False)
        return self._all(results.labelsAtPosition(point)) if results is not None else []

    def labels_in(self, rect: QgsRectangle) -> list[LabelRef]:
        results = self.canvas().labelingResults(False)
        return self._all(results.labelsWithinRect(rect)) if results is not None else []

    # -- musen ------------------------------------------------------------------------
    def canvasPressEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.press(event.mapPoint(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

    def canvasMoveEvent(self, event):  # noqa: N802
        if self._mode:
            self.drag_to(event.mapPoint(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        else:
            self.update_cursor(event.mapPoint())

    def canvasReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._mode:
            self.release(event.mapPoint(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.reset_selected()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear()
            event.accept()

    def deactivate(self):
        self.clear()
        super().deactivate()

    # -- var man tar tag i en text ---------------------------------------------------------
    def zone_at(self, point: QgsPointXY) -> Optional[str]:
        """Vad man tar tag i vid ``point``: ``RESIZE`` (ett hörn på en omformbar text), ``ROTATE`` (strax utanför ett hörn
        på en text som går att rotera) eller None."""
        if self.handle_at(point) is not None:
            return RESIZE
        return ROTATE if self.rotate_zone_at(point) is not None else None

    def update_cursor(self, point: QgsPointXY) -> None:
        """Markören följer vad den står över: rotationspil utanför ett hörn, diagonal pil på hörnet, annars handen."""
        zone = self.zone_at(point)
        if zone == RESIZE:  # hörnets pil beror på vilket hörn och hur texten är vriden: sätts om vid varje hörn
            handle = self.handle_at(point)
            self._set_cursor(QCursor(_diagonal_cursor(handle[2], handle[0].angle)))
        elif zone == ROTATE:
            self._set_cursor(self._rotate_cursor)
        else:
            self._set_cursor(self._default_cursor)
        self._zone = zone

    def _set_cursor(self, cursor: QCursor) -> None:
        self.current_cursor = cursor
        self.setCursor(cursor)

    # -- själva åtgärderna (kan anropas direkt i tester) -----------------------------------
    def handle_at(self, point: QgsPointXY) -> Optional[tuple[LabelRef, QgsPointXY, int]]:
        """Handtaget (hörnet) på en markerad, omformbar text som ligger under punkten: (texten, motsatt hörn, hörnets
        nummer). Hörnen följer textens vinkel."""
        tolerance = self.canvas().mapUnitsPerPixel() * HANDLE_PIXELS
        for label in self.selected:
            if label.table not in self.controller.RESIZABLE_LABELS:
                continue
            for index, (corner, opposite) in enumerate(_corners(label.rect, label.angle)):
                if corner.distance(point) <= tolerance:
                    return label, opposite, index
        return None

    def rotate_zone_at(self, point: QgsPointXY) -> Optional[LabelRef]:
        """Texten vars rotationszon ``point`` ligger i: strax utanför ett hörn (längre bort än handtaget, men inom
        ``ROTATE_PIXELS``) och bortom hörnet åt båda hållen, så att zonen ligger i hörnets utsida."""
        unit = self.canvas().mapUnitsPerPixel()
        inner, outer = unit * HANDLE_PIXELS, unit * ROTATE_PIXELS
        for label in self.selected:
            if label.table not in self.controller.ROTATABLE_LABELS:
                continue
            center = label.rect.center()
            local = _to_local(point, center, label.angle)
            half_w, half_h = label.rect.width() / 2, label.rect.height() / 2
            for corner, _ in _corners(label.rect, label.angle):
                distance = corner.distance(point)
                if not inner < distance <= outer:
                    continue
                sign_x, sign_y = _sign(_to_local(corner, center, label.angle).x()), _sign(_to_local(corner, center, label.angle).y())
                if (local.x() - sign_x * half_w) * sign_x >= 0 and (local.y() - sign_y * half_h) * sign_y >= 0:
                    return label
        return None

    def press(self, point: QgsPointXY, shift: bool = False) -> None:
        self._start, self._shift = point, shift
        handle = self.handle_at(point)
        if handle is not None:
            self._mode, self._resizing = RESIZE, handle[:2]
            return
        turn = self.rotate_zone_at(point)
        if turn is not None:
            center = turn.rect.center()
            self._mode = ROTATE
            self._rotating = (turn, math.degrees(math.atan2(point.y() - center.y(), point.x() - center.x())))
            return
        hit = next(iter(self.labels_at(point)), None)
        if hit is None:
            self._mode = "rect"
            return
        self._mode = "move"
        if hit.key not in {label.key for label in self.selected}:
            self.selected = [*self.selected, hit] if shift else [hit]
        elif shift:  # skift på en redan markerad text avmarkerar den
            self.selected = [label for label in self.selected if label.key != hit.key]
            self._mode = None
        self._show_selection()

    def _rotated_angle(self, point: QgsPointXY, shift: bool) -> Optional[float]:
        """Textens nya vinkel (grader moturs) när musen dras till ``point``: den gamla vinkeln plus hur långt musen vridits
        runt textens mitt, med skift låst till steg om ``SNAP_DEGREES``."""
        if self._rotating is None:
            return None
        label, start = self._rotating
        center = label.rect.center()
        now = math.degrees(math.atan2(point.y() - center.y(), point.x() - center.x()))
        angle = label.angle + (now - start)
        if shift:
            angle = round(angle / SNAP_DEGREES) * SNAP_DEGREES
        return angle

    def drag_to(self, point: QgsPointXY, shift: bool = False) -> None:
        if self._start is None:
            return
        if self._mode == "move":
            dx, dy = point.x() - self._start.x(), point.y() - self._start.y()
            self._ghosts.reset(Qgis.GeometryType.Polygon)
            for label in self.selected:
                self._ghosts.addGeometry(_polygon(_corner_points(_shifted(label.rect, dx, dy), label.angle)), None)
        elif self._mode == "rect":
            self._frame.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self._start, point)), None)
        elif self._mode == RESIZE and self._resizing is not None:
            _, corners = _frame_rect(self._resizing[1], point, self._resizing[0].angle)
            self._ghosts.setToGeometry(_polygon(corners), None)
        elif self._mode == ROTATE and self._rotating is not None:
            angle = self._rotated_angle(point, shift or self._shift)
            self._ghosts.setToGeometry(_polygon(_corner_points(self._rotating[0].rect, angle)), None)

    def release(self, point: QgsPointXY, shift: bool = False) -> None:
        start, mode, resizing, rotating = self._start, self._mode, self._resizing, self._rotating
        angle = self._rotated_angle(point, shift or self._shift) if mode == ROTATE else None
        self._mode, self._start, self._resizing, self._rotating = None, None, None, None
        self._ghosts.reset(Qgis.GeometryType.Polygon)
        self._frame.reset(Qgis.GeometryType.Polygon)
        if start is None or mode is None:
            return
        dragged = start.distance(point) > self.canvas().mapUnitsPerPixel() * DRAG_PIXELS
        if mode == RESIZE:
            if dragged and resizing is not None:
                rect, _ = _frame_rect(resizing[1], point, resizing[0].angle)
                self.resize_label(resizing[0], rect)
            return
        if mode == ROTATE:
            if dragged and rotating is not None and angle is not None:
                self.rotate_label(rotating[0], angle)
            return
        if mode == "move":
            if dragged:
                self.move_selected(point.x() - start.x(), point.y() - start.y())
            return
        if not dragged:  # klick på tomt ställe
            if not self._shift:
                self.selected = []
            self._show_selection()
            return
        inside = self.labels_in(QgsRectangle(start, point))
        keep = {label.key: label for label in self.selected} if self._shift else {}
        for label in inside:
            keep[label.key] = label
        self.selected = list(keep.values())
        self._show_selection()
        if not self.selected:
            self.report("Ingen text i rektangeln.", False)

    def move_selected(self, dx: float, dy: float) -> int:
        """Flyttar de markerade texterna. Returnerar hur många som flyttades."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna flytta text.", True)
            return 0
        moved = []
        for label in self.selected:
            center = label.rect.center()
            point = self.controller.move_label(label.table, label.fid, QgsPointXY(center.x() + dx, center.y() + dy))
            if point is not None:
                moved.append(LabelRef(label.table, label.fid,
                                      _shifted(label.rect, point.x() - center.x(), point.y() - center.y()), label.angle))
        self.selected = moved
        self._show_selection()
        return len(moved)

    def resize_label(self, label: LabelRef, rect: QgsRectangle) -> bool:
        """Omformar en texts ruta (bredden styr radbrytningen). Returnerar om det gjordes."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna ändra text.", True)
            return False
        if self.controller.resize_label(label.table, label.fid, rect) is None:
            return False
        self.selected = [LabelRef(label.table, label.fid, QgsRectangle(rect), label.angle) if item.key == label.key
                         else item for item in self.selected]
        self._show_selection()
        return True

    def rotate_label(self, label: LabelRef, angle: float) -> bool:
        """Vrider en text till ``angle`` grader moturs (0 = vågrät) runt dess mitt. Returnerar om det gjordes."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna ändra text.", True)
            return False
        stored = self.controller.rotate_label(label.table, label.fid, -angle, label.rect.center())
        if stored is None:
            return False
        self.selected = [LabelRef(label.table, label.fid, label.rect, _visual_angle(stored))
                         if item.key == label.key else item for item in self.selected]
        self._show_selection()
        return True

    def reset_selected(self) -> int:
        """Återställer markerade texter till automatisk placering."""
        if not self.selected:
            return 0
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna ändra text.", True)
            return 0
        for label in self.selected:
            self.controller.reset_label(label.table, label.fid)
        count = len(self.selected)
        self.clear()
        return count

    def clear(self) -> None:
        self.selected = []
        self._mode, self._start, self._resizing, self._rotating = None, None, None, None
        for band in (self._marks, self._ghosts, self._frame):
            band.reset(Qgis.GeometryType.Polygon)
        self._handles.reset(Qgis.GeometryType.Point)

    def _show_selection(self) -> None:
        self._marks.reset(Qgis.GeometryType.Polygon)
        self._handles.reset(Qgis.GeometryType.Point)
        for label in self.selected:
            self._marks.addGeometry(_polygon(_corner_points(label.rect, label.angle)), None)
            if label.table in self.controller.RESIZABLE_LABELS:
                for corner, _ in _corners(label.rect, label.angle):
                    self._handles.addPoint(corner)


# -- geometri ---------------------------------------------------------------------------------------
def _visual_angle(stored: float) -> float:
    """Verktygets vinkel (grader moturs, -180 till 180) för en lagrad vinkel (grader medurs, 0 till 360)."""
    return ((-stored + 180.0) % 360.0) - 180.0


def _sign(value: float) -> int:
    return 1 if value >= 0 else -1


def _to_local(point: QgsPointXY, center: QgsPointXY, angle: float) -> QgsPointXY:
    """``point`` i textens egna koordinater: origo i ``center``, x längs texten (vriden ``angle`` grader moturs)."""
    a = math.radians(angle)
    dx, dy = point.x() - center.x(), point.y() - center.y()
    return QgsPointXY(dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a))


def _from_local(x: float, y: float, center: QgsPointXY, angle: float) -> QgsPointXY:
    a = math.radians(angle)
    return QgsPointXY(center.x() + x * math.cos(a) - y * math.sin(a), center.y() + x * math.sin(a) + y * math.cos(a))


def _corner_points(rect: QgsRectangle, angle: float = 0.0) -> list[QgsPointXY]:
    """Rektangelns hörn (nedre vänstra, nedre högra, övre högra, övre vänstra), vridna ``angle`` grader moturs runt
    rektangelns mitt."""
    center, half_w, half_h = rect.center(), rect.width() / 2, rect.height() / 2
    return [_from_local(x, y, center, angle) for x, y in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h),
                                                           (-half_w, half_h))]


def _corners(rect: QgsRectangle, angle: float = 0.0) -> list[tuple[QgsPointXY, QgsPointXY]]:
    """Rektangelns fyra hörn (vridna ``angle`` grader moturs runt mitten), var och ett med det motsatta hörnet."""
    points = _corner_points(rect, angle)
    return [(points[0], points[2]), (points[1], points[3]), (points[2], points[0]), (points[3], points[1])]


def _polygon(points: list[QgsPointXY]) -> QgsGeometry:
    return QgsGeometry.fromPolygonXY([[*points, points[0]]])


def _frame_rect(fixed: QgsPointXY, point: QgsPointXY, angle: float) -> tuple[QgsRectangle, list[QgsPointXY]]:
    """Textrutan som spänns upp av det fasta hörnet ``fixed`` och musen ``point`` i textens egna led (vriden ``angle`` grader
    moturs): rutan utan rotation (runt sin mitt, för styrenheten) och dess fyra hörn i kartan (för förhandsvisningen). Utan
    rotation är det rektangeln mellan de två punkterna."""
    local = _to_local(point, fixed, angle)
    corners = [_from_local(x, y, fixed, angle) for x, y in ((0, 0), (local.x(), 0), (local.x(), local.y()), (0, local.y()))]
    center = _from_local(local.x() / 2, local.y() / 2, fixed, angle)
    half_w, half_h = abs(local.x()) / 2, abs(local.y()) / 2
    return QgsRectangle(center.x() - half_w, center.y() - half_h, center.x() + half_w, center.y() + half_h), corners


def _shifted(rect: QgsRectangle, dx: float, dy: float) -> QgsRectangle:
    return QgsRectangle(rect.xMinimum() + dx, rect.yMinimum() + dy, rect.xMaximum() + dx, rect.yMaximum() + dy)


def _diagonal_cursor(corner: int, angle: float) -> Qt.CursorShape:
    """Diagonal pil för ett hörn: hörnen 0 och 2 ligger längs "/" och 1 och 3 längs "\" när texten är vågrät; en text vriden
    mer än 45 grader (och mindre än 135) har bytt riktning."""
    slash = corner in (0, 2)
    if 45 <= angle % 180 < 135:
        slash = not slash
    return Qt.CursorShape.SizeBDiagCursor if slash else Qt.CursorShape.SizeFDiagCursor


def _rotation_cursor() -> QCursor:
    """Markören som visas utanför ett hörn: den vanliga rotationsikonen, en nästan hel cirkelbåge med en pilspets i änden
    (svart med vit kant, så att den syns mot både ljus och mörk bakgrund)."""
    size, center, radius = 32, 16.0, 9.0
    start, sweep = 80.0, -280.0  # grader moturs från klockan 3; negativt sweep = medurs
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    arc = QPainterPath()
    arc.arcMoveTo(center - radius, center - radius, 2 * radius, 2 * radius, start)
    arc.arcTo(center - radius, center - radius, 2 * radius, 2 * radius, start, sweep)
    end = math.radians(start + sweep)
    # pilspetsen i bågens slut: spetsen pekar längs bågen, basen ligger tvärs över den
    point = QPointF(center + radius * math.cos(end), center - radius * math.sin(end))
    along = QPointF(math.sin(end), math.cos(end))  # riktningen medurs i bildkoordinater (y nedåt)
    across = QPointF(math.cos(end), -math.sin(end))
    head = QPolygonF([point + along * 5.0, point + across * 3.5, point - across * 3.5])
    for color, width in ((QColor(255, 255, 255), 4.0), (QColor(0, 0, 0), 1.8)):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # bågen är bara en linje: fylld blir den en svart klump
        painter.drawPath(arc)
        painter.setBrush(color)  # pilspetsen är fylld
        painter.drawPolygon(head)
    painter.end()
    return QCursor(pixmap, size // 2, size // 2)
