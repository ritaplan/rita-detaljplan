"""Höjd (tredje dimensionen) för planbestämmelser, enligt Lantmäteriets vägledning för detaljplan (avsnitt 3.2.2).

En bestämmelse har två höjder i meter i höjdsystemet RH2000 (EPSG:5613), båda valfria (``hojdUnderkant`` och
``hojdOverkant`` i tabellen ``bestammelse``):

  * **ingen** höjd: bestämmelsen gäller obegränsat i höjdled, som en vanlig yta (2D);
  * **bara en** höjd: *yta med höjdvärde* och vertikal avgränsning. Bara överkant: bestämmelsen gäller inte ovanför
    höjden (``uppåt``); bara underkant: gäller inte under (``nedåt``);
  * **båda**: en *kropp* (ett lodrätt prisma av ytan). Vertikal avgränsning får då inte anges (DP-0015, DP-0016).

Modulen är ren Python (ingen QGIS): intervallen, avgränsningen och kroppens ytor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

UPWARD, DOWNWARD = "uppåt", "nedåt"
FLAT, HEIGHT, SOLID = "2d", "yta", "kropp"  # hur bestämmelsens geometri levereras
HEIGHT_SYSTEM = "EPSG:5613"  # RH2000


def number(value) -> Optional[float]:
    """Höjden som tal, eller None om den är tom eller inte ett tal (komma accepteras som decimaltecken)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None  # inte NaN eller oändligt


@dataclass(frozen=True)
class Extent:
    """Hur långt bestämmelsen gäller i höjdled. ``None`` = obegränsat åt det hållet."""
    lower: Optional[float] = None  # underkant
    upper: Optional[float] = None  # överkant

    @property
    def kind(self) -> str:
        if self.lower is not None and self.upper is not None:
            return SOLID
        return HEIGHT if self.lower is not None or self.upper is not None else FLAT

    @property
    def limited(self) -> bool:
        return self.kind != FLAT

    @property
    def limit(self) -> Optional[str]:
        """Den vertikala avgränsningen som hör till höjderna: bara överkant = uppåt, bara underkant = nedåt, annars
        ingen (en kropp får inte ha någon, och utan höjd finns det inget att härleda)."""
        if self.kind != HEIGHT:
            return None
        return UPWARD if self.upper is not None else DOWNWARD

    @property
    def height(self) -> Optional[float]:
        """Höjdvärdet som en yta med höjd får på sina koordinater (None för kropp och 2D)."""
        if self.kind != HEIGHT:
            return None
        return self.upper if self.upper is not None else self.lower

    @property
    def consistent(self) -> bool:
        """Underkanten ligger under överkanten (en kropp med tjocklek)."""
        return self.lower is None or self.upper is None or self.lower < self.upper

    def overlaps(self, other: "Extent") -> bool:
        """Om de två sträckorna delar höjdled. Gränser som bara möts (garaget upp till 0, gården från 0) är inget överlapp."""
        inf = float("inf")
        low = max(-inf if self.lower is None else self.lower, -inf if other.lower is None else other.lower)
        high = min(inf if self.upper is None else self.upper, inf if other.upper is None else other.upper)
        return low < high

    def text(self) -> str:
        """Kort text för meddelanden, t.ex. "−6,0 till 0,0 m"."""
        def show(value: float) -> str:
            return f"{value:.1f}".replace("-", "−").replace(".", ",")
        if self.kind == SOLID:
            return f"{show(self.lower)} till {show(self.upper)} m"
        if self.kind == HEIGHT:
            return f"{'under' if self.upper is not None else 'över'} {show(self.height)} m"
        return "obegränsad höjd"


def extent_of(row: dict) -> Extent:
    """Höjderna på en rad i tabellen ``bestammelse``."""
    return Extent(number(row.get("hojdUnderkant")), number(row.get("hojdOverkant")))


def hull(extents: Iterable[Extent]) -> Extent:
    """Det som en yta med flera bestämmelser täcker i höjdled: obegränsat åt ett håll om någon bestämmelse är det.
    En yta utan bestämmelser (ännu) är obegränsad: den kan hamna var som helst."""
    found = list(extents)
    if not found:
        return Extent()
    lowers, uppers = [e.lower for e in found], [e.upper for e in found]
    return Extent(None if any(x is None for x in lowers) else min(lowers),
                  None if any(x is None for x in uppers) else max(uppers))


def area_extent(rows: Iterable[dict]) -> Extent:
    return hull(extent_of(row) for row in rows)


# -- kroppens ytor ------------------------------------------------------------------------------
def solid_faces(rings: list[list[list[float]]], lower: float, upper: float) -> list[list[list[list[float]]]]:
    """Ytorna som sluter en kropp av en yta mellan två höjder, som GeoJSON-polygoner med tre koordinater ([x, y, z]).

    ``rings`` är ytans ringar som slutna listor av [x, y]: ytterringen moturs, hålen medurs (så som exporten skriver
    dem). Kroppen får en botten (vänd nedåt), ett lock (vänt uppåt) och en sidoyta per kant, alla med normalen utåt.
    Botten och lock bär hålen som egna ringar, och hålens kanter får egna sidoytor."""
    top = [[[x, y, upper] for x, y in ring] for ring in rings]
    bottom = [[[x, y, lower] for x, y in reversed(ring)] for ring in rings]
    faces = [bottom, top]
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            faces.append([[[x0, y0, lower], [x1, y1, lower], [x1, y1, upper], [x0, y0, upper], [x0, y0, lower]]])
    return faces


def surface_ring(ring: list[list[float]], height: float) -> list[list[float]]:
    """En ring med samma höjd på alla punkter (en yta med höjdvärde)."""
    return [[x, y, height] for x, y in ring]


# -- läsa en 3D-geometri ----------------------------------------------------------------------
def _flat(face: list[list[list[float]]]) -> bool:
    return len({round(p[2], 6) for ring in face for p in ring if len(p) > 2}) <= 1


def _vertical(face: list[list[list[float]]]) -> bool:
    """Alla punkter ligger på en lodrät linje i planet (x, y) eller i ett lodrätt plan: sidoyta."""
    points = [(p[0], p[1]) for ring in face for p in ring]
    if len(set((round(x, 6), round(y, 6)) for x, y in points)) <= 2:
        return True
    (x0, y0), (x1, y1) = points[0], next(((x, y) for x, y in points if (x, y) != points[0]), points[0])
    return all(abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) < 1e-6 for x, y in points)


def read_solid(faces: list) -> tuple[Optional[float], Optional[float], list[list[list[float]]], bool]:
    """Tolkar en kropp (en lista ytor med [x, y, z]-koordinater): (underkant, överkant, ytterkontur-ringar som en
    polygon, om den är ett lodrätt prisma).

    Underkant och överkant är lägsta och högsta höjden. Konturen är ytan i botten eller locket (den största av de
    vågräta ytorna med lägsta höjden), med hål. Är kroppen inte ett lodrätt prisma (snedställda ytor) används
    ändå samma kontur, men det sista värdet är False så att anroparen kan varna."""
    zs = [p[2] for face in faces for ring in face for p in ring if len(p) > 2]
    if not zs:
        return None, None, [], False
    lower, upper = min(zs), max(zs)
    prism = all(_flat(face) or _vertical(face) for face in faces)
    footprint = [face for face in faces if _flat(face) and abs(face[0][0][2] - lower) < 1e-6]
    if not footprint:
        footprint = [face for face in faces if _flat(face)]
    best = max(footprint, key=lambda face: abs(_area(face[0])), default=None)
    rings = [[[x, y] for x, y, *_ in ring] for ring in best] if best else []
    return lower, upper, rings, prism


def _area(ring: list[list[float]]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2.0
