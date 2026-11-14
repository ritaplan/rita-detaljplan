"""Topologikontroll: brytpunkter och små glapp mellan planområde, användningsytor och egenskapsytor.

Analysen föreslår ändringar; ingenting ändras förrän användaren valt vilka som ska göras (``apply_to_geometry``):

  * **Brytpunkter ska sammanfalla.** En brytpunkt i en användningsyta som ligger nära (men inte exakt på) en brytpunkt i
    planområdet flyttas dit, och ligger den nära planområdets gräns flyttas den ända fram till gränsen. Planområdet har
    alltid företräde (planområde > användning > egenskap), i linje med hierarkin på kartan.
  * **Gemensamma brytpunkter ska finnas i båda ytorna.** Ligger en brytpunkt hos planområdet eller en yta med högre
    företräde vid en annan ytas gräns, utan att ytan har en brytpunkt där (en T-skarv), läggs en till.
  * **Små glapp** mellan användningsytor (och mellan egenskap och användning) stängs: en brytpunkt som ligger inom
    toleransen från en annan ytas gräns, utan att ligga på den, flyttas till den. Mellan ytor i samma lager flyttas den
    senare ytans brytpunkt till den tidigare (så att bara en av dem ändras). Egenskapsytor anpassas på samma sätt till
    planområdet, användningsytorna och tidigare egenskapsytor.
  * **Dubblerade brytpunkter** (två i rad som ligger inom en centimeter från varandra) tas bort.

Varje förslag är antingen *säkert* (en centimeter eller mindre: rättas automatiskt) eller *att granska* (större än så, upp
till toleransen). Det styr hur dialogen visar det (se ``Change.tier``).

Ytor utan utbredning (area 0) hoppas över: de är skräp som ska bort (se ``is_degenerate``), inte något som ska
anpassas. Rena geometriberäkningar (QgsGeometry) utan koppling till lager; kontrollen av att en ändring inte ger en ogiltig
geometri görs när ändringen genomförs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY

DEFAULT_TOLERANCE = 0.10  # m: som reglerna (10 cm åt båda håll, se core.validation); närmare än så räknas ett avstånd
#                          som ett glapp/en avvikelse och inte som avsiktligt
EXACT = 1e-6  # m: så nära räknas brytpunkter som sammanfallande
NOISE = 0.001  # m: en avvikelse under 1 mm ser ingen och är bara avrundning: rättas, men visas som "under 1 mm"
EMPTY_AREA = 0.01  # m²: en yta som inte är större har ingen utbredning (samma gräns som core.rules.MIN_OVERLAP)

SAFE = 0.01  # m: en ändring på högst en centimeter är säker och kan göras utan granskning
DUPLICATE = 0.01  # m: två brytpunkter i rad som ligger så nära varandra är en dubblett
TIER_AUTO, TIER_REVIEW = "auto", "granska"

SNAP_VERTEX, SNAP_EDGE, ADD_VERTEX, REMOVE_VERTEX = "brytpunkt", "gräns", "planbrytpunkt", "dubblett"
KIND_TITLES = {SNAP_VERTEX: "Flytta brytpunkt till brytpunkt", SNAP_EDGE: "Stäng glapp mot gräns",
               ADD_VERTEX: "Lägg till gemensam brytpunkt", REMOVE_VERTEX: "Ta bort dubblerad brytpunkt"}
TARGET_TITLES = {"detaljplan": "planområdet", "anvandning_yta": "användningsområdet", "egenskap_yta": "egenskapsområdet"}
TABLE_TITLES = {"anvandning_yta": "Användningsområde", "egenskap_yta": "Egenskapsområde"}


@dataclass(frozen=True)
class Change:
    """En föreslagen ändring av en yta: flytta en brytpunkt (``old`` → ``new``), lägga till en (``old`` är None) eller ta
    bort en (``new`` är None)."""
    kind: str
    table: str
    fid: int
    old: Optional[tuple]
    new: Optional[tuple]
    distance: float  # m: hur långt brytpunkten flyttas (0 vid tillägg på gränsen)
    reference: str  # vad den anpassas till: "detaljplan", "anvandning_yta" eller "egenskap_yta"

    @property
    def title(self) -> str:
        return KIND_TITLES[self.kind]

    @property
    def tier(self) -> str:
        """``TIER_AUTO`` (högst en centimeter: säkert, görs utan granskning) eller ``TIER_REVIEW`` (större, att granska)."""
        return TIER_AUTO if self.distance <= SAFE else TIER_REVIEW

    @property
    def noise(self) -> bool:
        """Avvikelsen är under 1 mm: avrundning som ingen ser, men som ändå gör att gränserna inte sammanfaller exakt."""
        return self.distance <= NOISE

    @property
    def text(self) -> str:
        target = TARGET_TITLES.get(self.reference, self.reference)
        length = length_text(self.distance)
        if self.kind == SNAP_VERTEX:
            return f"Flytta brytpunkten {length} till {target}s brytpunkt"
        if self.kind == SNAP_EDGE:
            return f"Stäng glapp på {length} mot {target}s gräns"
        if self.kind == REMOVE_VERTEX:
            return f"Ta bort en brytpunkt som ligger {length} från den förra"
        return f"Lägg till en brytpunkt där {target} har en ({length} från ytans kant)"

    @property
    def where(self) -> str:
        return TABLE_TITLES.get(self.table, self.table)


def length_text(meters: float) -> str:
    """Ett avstånd så att det går att läsa: "under 1 mm", "0,4 mm" … "7 cm", "1,2 m" (aldrig "0 cm")."""
    if meters <= NOISE:
        return "under 1 mm"
    if meters < 0.01:
        return f"{meters * 1000:.1f}".replace(".", ",") + " mm"
    if meters < 1:
        return f"{meters * 100:.0f} cm"
    return f"{meters:.1f}".replace(".", ",") + " m"


def summarize(changes: list[Change]) -> str:
    """En rad för alla förslag som gäller samma yta: "Justera 18 brytpunkter (som mest under 1 mm) mot
    planområdets gräns". Ett enda förslag får sin egen text."""
    if len(changes) == 1:
        return changes[0].text
    moves = [c for c in changes if c.kind in (SNAP_VERTEX, SNAP_EDGE)]
    adds = [c for c in changes if c.kind == ADD_VERTEX]
    removes = [c for c in changes if c.kind == REMOVE_VERTEX]
    parts = []
    if moves:
        targets = " och ".join(sorted({TARGET_TITLES.get(c.reference, c.reference) + "s" for c in moves}))
        parts.append(f"justera {len(moves)} brytpunkter (som mest {length_text(max(c.distance for c in moves))}) "
                     f"mot {targets} gräns")
    if adds:
        parts.append(f"lägg till {len(adds)} brytpunkter")
    if removes:
        parts.append(f"ta bort {len(removes)} dubblerade brytpunkter")
    text = " och ".join(parts)
    return text[:1].upper() + text[1:]


def is_degenerate(geometry: Optional[QgsGeometry]) -> bool:
    """En yta utan utbredning (area 0 också efter reparation, eller en remsa som är smalare än en millimeter i snitt, t.ex.
    en spets som går ut och tillbaka längs en gräns). Den innehåller ingen information och räknas varken som förslag eller som något andra ytor anpassas till."""
    if geometry is None or geometry.isNull() or geometry.isEmpty() or geometry.type() != Qgis.GeometryType.Polygon:
        return False
    if abs(geometry.area()) > EMPTY_AREA:
        # en remsa smalare än en millimeter i snitt (2 x area / omkrets) är en linje, inte en yta
        return geometry.isGeosValid() and geometry.length() > 0 and 2 * geometry.area() / geometry.length() <= NOISE
    if geometry.isGeosValid():
        return True
    # en självkorsande gräns (en fjärilsform) kan få area 0 i summan men har verklig utbredning: reparera först
    fixed = geometry.makeValid()
    return fixed.isNull() or fixed.isEmpty() or fixed.area() <= EMPTY_AREA


# -- geometrihjälp ----------------------------------------------------------------------------
def _parts(geometry: Optional[QgsGeometry]) -> list[QgsGeometry]:
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return []
    return [part for part in geometry.asGeometryCollection() if not part.isEmpty()]


def vertices(geometry: Optional[QgsGeometry]) -> list[QgsPointXY]:
    """Alla brytpunkter (utan att räkna slutpunkten som är samma som startpunkten i en ring två gånger)."""
    points: list[QgsPointXY] = []
    for part in _parts(geometry):
        if part.type() == Qgis.GeometryType.Polygon:
            rings = part.asPolygon()
            for ring in rings:
                points += ring[:-1]
        elif part.type() == Qgis.GeometryType.Line:
            points += part.asPolyline()
    return points


def _boundary(geometry: Optional[QgsGeometry]) -> Optional[QgsGeometry]:
    parts = _parts(geometry)
    if not parts:
        return None
    lines = [p.convertToType(Qgis.GeometryType.Line) if p.type() == Qgis.GeometryType.Polygon else p for p in parts]
    return QgsGeometry.collectGeometry([l for l in lines if l is not None and not l.isNull()]) if lines else None


def _nearest(points: Iterable[QgsPointXY], target: QgsPointXY) -> tuple[Optional[QgsPointXY], float]:
    best, best_d = None, float("inf")
    for point in points:
        d = point.distance(target)
        if d < best_d:
            best, best_d = point, d
    return best, best_d


def _key(point: QgsPointXY) -> tuple:
    return (round(point.x(), 9), round(point.y(), 9))


# -- analys -------------------------------------------------------------------------------------
@dataclass
class Reference:
    """Det ett lager anpassas till: brytpunkter och gräns hos ytor med högre företräde."""
    name: str
    points: list
    boundary: Optional[QgsGeometry]
    fid: Optional[int] = None


def _references(name: str, geometry: Optional[QgsGeometry], fid: Optional[int] = None) -> Optional[Reference]:
    points = vertices(geometry)
    boundary = _boundary(geometry)
    return Reference(name, points, boundary, fid) if points and boundary is not None else None


def _snap_vertex(vertex: QgsPointXY, refs: list[Reference], tolerance: float):
    """Bästa förslaget för en brytpunkt: närmaste brytpunkt (inom toleransen), annars närmaste punkt på en gräns."""
    if not refs:
        return None
    if any(vertex.distance(p) <= EXACT for r in refs for p in r.points):
        return None  # sammanfaller redan med en brytpunkt
    best = None
    for ref in refs:
        point, d = _nearest(ref.points, vertex)
        if point is not None and d <= tolerance and (best is None or d < best[0]):
            best = (d, SNAP_VERTEX, point, ref)
    if best is not None:
        return best
    for ref in refs:
        if ref.boundary is None:
            continue
        nearest = ref.boundary.nearestPoint(QgsGeometry.fromPointXY(vertex))
        if nearest.isNull():
            continue
        point = nearest.asPoint()
        d = vertex.distance(point)
        if EXACT < d <= tolerance and (best is None or d < best[0]):
            best = (d, SNAP_EDGE, point, ref)
    return best


def _usable(geometry: Optional[QgsGeometry]) -> bool:
    return geometry is not None and not geometry.isNull() and not geometry.isEmpty() and not is_degenerate(geometry)


def analyze(plan: Optional[QgsGeometry], uses: list[tuple], properties: list[tuple],
            tolerance: float = DEFAULT_TOLERANCE) -> list[Change]:
    """Föreslår ändringar. ``uses`` och ``properties`` är listor av ``(fid, geometri)``; ordningen i listan avgör
    vilken av två lika viktiga ytor som anpassar sig till vilken (den senare till den tidigare). Företräde: planområde,
    användning, egenskap."""
    changes: list[Change] = []
    plan_ref = _references("detaljplan", plan)

    ordered_uses = [(fid, g) for fid, g in uses if _usable(g)]
    for index, (fid, geometry) in enumerate(ordered_uses):
        refs = [plan_ref] if plan_ref else []
        refs += [r for r in (_references("anvandning_yta", g) for _, g in ordered_uses[:index]) if r]
        changes += _area_changes("anvandning_yta", fid, geometry, refs, tolerance)

    use_refs = [r for r in (_references("anvandning_yta", g) for _, g in ordered_uses) if r]
    ordered_properties = [(fid, g) for fid, g in properties if _usable(g)]
    for index, (fid, geometry) in enumerate(ordered_properties):
        refs = ([plan_ref] if plan_ref else []) + use_refs
        refs += [r for r in (_references("egenskap_yta", g) for _, g in ordered_properties[:index]) if r]
        changes += _area_changes("egenskap_yta", fid, geometry, refs, tolerance)
    return changes


def _area_changes(table: str, fid: int, geometry: QgsGeometry, refs: list[Reference], tolerance: float) -> list[Change]:
    """Alla förslag för en yta: dubbletter först, sedan brytpunkter som flyttas och gemensamma som läggs till. Brytpunkter
    som tas bort som dubbletter flyttas inte också."""
    removed = _duplicate_vertices(table, fid, geometry)
    gone = {c.old for c in removed}
    found = list(removed)
    moves = [c for c in _vertex_changes(table, fid, geometry, refs, tolerance) if c.old not in gone]
    found += moves
    found += _added_vertices(table, fid, geometry, refs, tolerance, moves)
    return found


def _vertex_changes(table: str, fid: int, geometry: QgsGeometry, refs: list[Reference], tolerance: float) -> list[Change]:
    found: list[Change] = []
    for vertex in vertices(geometry):
        best = _snap_vertex(vertex, refs, tolerance)
        if best is None:
            continue
        distance, kind, point, ref = best
        found.append(Change(kind, table, fid, _key(vertex), _key(point), distance, ref.name))
    return found


def _added_vertices(table: str, fid: int, geometry: QgsGeometry, refs: list[Reference], tolerance: float,
                    existing: list[Change]) -> list[Change]:
    """Brytpunkter hos planområdet eller en yta med högre företräde som ligger vid ytans gräns men saknas i ytan (en
    T-skarv): ytan får en brytpunkt där, så att de delar den."""
    boundary = _boundary(geometry)
    if boundary is None:
        return []
    own = vertices(geometry)
    box = geometry.boundingBox()
    box.grow(tolerance)
    moved_to = {c.new for c in existing if c.fid == fid and c.table == table and c.new is not None}
    found, seen = [], set()
    for ref in refs:
        for point in ref.points:
            if not box.contains(point):
                continue  # för långt bort för att kunna ligga vid ytans gräns
            key = _key(point)
            if key in moved_to or key in seen or any(point.distance(v) <= tolerance for v in own):
                continue  # ytan har redan (eller får) en brytpunkt där
            nearest = boundary.nearestPoint(QgsGeometry.fromPointXY(point))
            if nearest.isNull():
                continue
            d = point.distance(nearest.asPoint())
            if d <= tolerance:
                found.append(Change(ADD_VERTEX, table, fid, None, key, d, ref.name))
                seen.add(key)
    return found


def tidy(geometry: QgsGeometry, others: list[QgsGeometry], tolerance: float = SAFE) -> tuple[QgsGeometry, int]:
    """Rättar en nyritad eller ändrad ytas brus: brytpunkter inom ``tolerance`` (förval en centimeter, det osynliga)
    från en annan ytas brytpunkt eller gräns flyttas dit, gemensamma brytpunkter läggs till och dubbletter tas bort.
    Bara ``geometry`` ändras, aldrig ``others`` (planområdet och de ytor som redan finns). Returnerar (ny geometri,
    antal ändringar); utan ändringar samma geometri."""
    if not _usable(geometry) or geometry.type() != Qgis.GeometryType.Polygon:
        return geometry, 0
    box = geometry.boundingBox()
    box.grow(tolerance * 2)
    refs = [r for r in (_references("granne", g) for g in others
                        if g is not None and not g.isNull() and not g.isEmpty() and g.boundingBox().intersects(box)) if r]
    changes = _area_changes("", 0, geometry, refs, tolerance)
    if not changes:
        return geometry, 0
    fixed, done, _skipped = apply_to_geometry(geometry, changes)
    return (fixed, done) if done else (geometry, 0)


def _duplicate_vertices(table: str, fid: int, geometry: QgsGeometry) -> list[Change]:
    """Två brytpunkter i rad (också över ringens skarv) som ligger inom ``DUPLICATE`` från varandra: den andra är en
    dubblett och tas bort. En ring behåller alltid minst tre brytpunkter."""
    found: list[Change] = []
    for part in _parts(geometry):
        if part.type() != Qgis.GeometryType.Polygon:
            continue
        for ring in part.asPolygon():
            points = ring[:-1]
            keep = len(points)
            for i, point in enumerate(points):
                following = points[(i + 1) % len(points)]
                d = point.distance(following)
                if keep > 3 and d <= DUPLICATE:
                    found.append(Change(REMOVE_VERTEX, table, fid, _key(following), None, d, ""))
                    keep -= 1
    return found


# -- genomförande -------------------------------------------------------------------------------
def apply_to_geometry(geometry: QgsGeometry, changes: list[Change]) -> tuple[QgsGeometry, int, int]:
    """Genomför ändringarna på en geometri (flytta, lägga till eller ta bort brytpunkter). Returnerar (ny geometri,
    antal gjorda, antal hoppade över).

    Brytpunkterna hittas via sina koordinater, så ordningen mellan ändringarna spelar ingen roll. En ändring som
    skulle ge en ogiltig geometri (t.ex. en korsande gräns) hoppas över."""
    current = QgsGeometry(geometry)
    done = skipped = 0
    for change in changes:
        trial = QgsGeometry(current)
        if change.new is None:  # ta bort en dubblett
            _, at, _, _, distance = _closest_vertex(trial, QgsPointXY(*change.old))
            ok = at >= 0 and distance <= 1e-4 and trial.deleteVertex(at)
        elif change.old is None:  # lägg till en gemensam brytpunkt
            target = QgsPointXY(*change.new)
            _, _, after, _ = _segment(trial, target)
            ok = after >= 0 and trial.insertVertex(target.x(), target.y(), after)
        else:  # flytta
            target = QgsPointXY(*change.new)
            _, at, _, _, distance = _closest_vertex(trial, QgsPointXY(*change.old))
            ok = at >= 0 and distance <= 1e-4 and trial.moveVertex(target.x(), target.y(), at)
        if ok and trial.isGeosValid() and not trial.isEmpty():
            current = trial
            done += 1
        else:
            skipped += 1
    return current, done, skipped


def _closest_vertex(geometry: QgsGeometry, point: QgsPointXY):
    found, at, before, after, sqr = geometry.closestVertex(point)
    return found, at, before, after, sqr ** 0.5 if sqr >= 0 else float("inf")


def _segment(geometry: QgsGeometry, point: QgsPointXY):
    sqr, nearest, after, left = geometry.closestSegmentWithContext(point)
    return sqr, nearest, after, left
