"""Import av en leverans i Lantmäteriets JSON-format (samma ``FeatureCollection`` som ``core.export_ngp`` skriver,
mediatyp ``application/vnd.lm.detaljplan.v4+json``) till en ny, tom detaljplan i pluginet.

Filen kan komma från Rita Detaljplan självt, eller från ett annat verktyg (t.ex. ArcGIS Pro) som levererar enligt
Nationell informationsspecifikation Detaljplan 4.1 – bara strukturen följs, inte var filen kom ifrån.

Detta är den rena tolkningen av filen: geometrier byggs upp och planbestämmelseobjekten grupperas till de ytor
(eller linjer) de hör till (en yta per unik geometri; bara ytor med minst en bestämmelse finns i leveransen, precis
som vid export). Vilken katalogpost varje bestämmelse motsvarar, och själva skrivandet till planens lager, sköts av
``PlanController.import_ngp`` (som har tillgång till den laddade planbestämmelsekatalogen och redigeringsbufferten).
Modulen ändrar ingenting: den bara läser och bygger geometrier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from qgis.core import QgsGeometry, QgsPointXY

from . import bestammelse as bm
from . import catalog as cat
from . import vertical

USE_TYPE = "användningsbestämmelse"
PROPERTY_TYPE = "egenskapsbestämmelse"


class ImportError_(ValueError):
    """Filen är inte en leverans i det förväntade formatet."""


@dataclass
class ImportedProvision:
    """En rad i tabellen ``bestammelse``, tolkad ur ett planbestämmelseobjekt."""
    catalog_id: str
    formulering: str
    values: list[dict]  # samma form som ``bestammelsevarde`` (beskrivning/variabelvarde/vardetyp/enhet)
    motiv: Optional[str] = None
    giltighetstid: Optional[int] = None
    borjar_galla_efter: Optional[int] = None
    extent: vertical.Extent = field(default_factory=vertical.Extent)  # höjd (kropp eller yta med höjdvärde)
    vertikal_avgransning: Optional[str] = None  # uppåt/nedåt för en yta utan höjdvärde


@dataclass
class ImportedArea:
    """En yta, linje eller punkt, med de bestämmelser som hör till den (samma geometri i leveransen)."""
    table: str  # "anvandning_yta" | "egenskap_yta" | "egenskap_linje" | "egenskap_punkt"
    geometry: QgsGeometry
    sekundar: bool = False
    provisions: list[ImportedProvision] = field(default_factory=list)


@dataclass
class ImportedPlan:
    attrs: dict[str, Any]  # kommun, namn, syfte, status, typ, beteckning …: skrivs som planlagrets attribut
    geometry: QgsGeometry
    decision: Optional[dict] = None  # första beslutsinformationen, i beslutsinformation-tabellens form
    documents: list[dict] = field(default_factory=list)  # dokument-tabellens form
    areas: list[ImportedArea] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# -- geometri ---------------------------------------------------------------------------------
def _points(coordinates) -> list[QgsPointXY]:
    """Punkterna i planet: höjden (en tredje koordinat) hör inte till ytan och läses separat."""
    return [QgsPointXY(float(c[0]), float(c[1])) for c in coordinates]


def _part_geometry(position: dict) -> Optional[QgsGeometry]:
    kind = position.get("type")
    if kind == "Polygon":
        rings = [_points(ring) for ring in position.get("coordinates") or []]
        return QgsGeometry.fromPolygonXY(rings) if rings and rings[0] else None
    if kind == "LineString":
        points = _points(position.get("coordinates") or [])
        return QgsGeometry.fromPolylineXY(points) if len(points) >= 2 else None
    if kind == "Point":
        coordinates = position.get("coordinates") or []
        return QgsGeometry.fromPointXY(QgsPointXY(float(coordinates[0]), float(coordinates[1]))) \
            if len(coordinates) >= 2 else None
    # flerdelade (multiyta, multilinje, multipunkt i NGP:s schema): delarna blir en flerdelad geometri
    if kind == "MultiPolygon":
        polygons = [[_points(ring) for ring in polygon] for polygon in position.get("coordinates") or []]
        polygons = [polygon for polygon in polygons if polygon and polygon[0]]
        return QgsGeometry.fromMultiPolygonXY(polygons) if polygons else None
    if kind == "MultiLineString":
        lines = [_points(line) for line in position.get("coordinates") or []]
        lines = [line for line in lines if len(line) >= 2]
        return QgsGeometry.fromMultiPolylineXY(lines) if lines else None
    if kind == "MultiPoint":
        points = _points([c for c in position.get("coordinates") or [] if len(c) >= 2])
        return QgsGeometry.fromMultiPointXY(points) if points else None
    return None


@dataclass
class _Part:
    """En del av en geometri i leveransen: ytan i planet, och höjden om delen är en kropp eller en yta med höjdvärde."""
    geometry: QgsGeometry
    lower: Optional[float] = None  # kropp: underkant
    upper: Optional[float] = None  # kropp: överkant
    height: Optional[float] = None  # yta med höjdvärde
    simplified: bool = False  # en kropp som inte är ett lodrätt prisma, förenklad till ett


def _height_of(position: dict) -> Optional[float]:
    """Höjdvärdet på en yta (tredje koordinaten på första punkten), om ytan har ett. En flerdelad ytas första del räknas."""
    coordinates = position.get("coordinates") or []
    if position.get("type") == "MultiPolygon":
        coordinates = coordinates[0] if coordinates else []
    for ring in coordinates:
        for point in ring:
            return vertical.number(point[2]) if len(point) > 2 else None
    return None


def _part(description: dict) -> Optional[_Part]:
    geometry = description.get("geometri") or {}
    position = geometry.get("position") or {}
    if geometry.get("typ") == "kropp" or (geometry.get("typ") is None and position.get("type") == "MultiPolygon"
                                          and any(len(p) > 2 for f in position.get("coordinates") or []
                                                  for ring in f for p in ring)):
        lower, upper, rings, prism = vertical.read_solid(position.get("coordinates") or [])
        outline = QgsGeometry.fromPolygonXY([_points(ring) for ring in rings]) if rings and rings[0] else None
        return _Part(outline, lower, upper, simplified=not prism) if outline is not None and not outline.isEmpty() \
            else None
    flat = _part_geometry(position)
    if flat is None or flat.isEmpty():
        return None
    return _Part(flat, height=_height_of(position) if position.get("type") in ("Polygon", "MultiPolygon") else None)


def build_geometry(descriptions: list[dict]) -> Optional[QgsGeometry]:
    """Slår ihop delarna av en ``plangeometri``/``bestammelsegeometri`` (en post per del, se ``export_ngp``) till en
    enda (multi-)geometri. Ger None om den saknar giltiga delar. Höjder ignoreras (se ``build_area``)."""
    parts = [part.geometry for part in (_part(item) for item in descriptions or []) if part is not None]
    if not parts:
        return None
    geometry = QgsGeometry.unaryUnion(parts) if len(parts) > 1 else parts[0]
    geometry.convertToMultiType()
    return geometry


def build_area(descriptions: list[dict], limit: Optional[str] = None) -> tuple[Optional[QgsGeometry], vertical.Extent,
                                                                           list[str]]:
    """Som ``build_geometry`` för en bestämmelse, men också höjden: (ytan i planet, höjderna, anmärkningar).

    En kropp ger underkant och överkant. En yta med höjdvärde ger underkant (``limit`` nedåt) eller överkant (uppåt);
    utan vertikal avgränsning vet man inte åt vilket håll den gäller, så höjdvärdet ignoreras (med en anmärkning).
    Har delarna olika höjder gäller det de tillsammans täcker (``vertical.hull``)."""
    parts = [part for part in (_part(item) for item in descriptions or []) if part is not None]
    notes: list[str] = []
    extents = []
    for part in parts:
        if part.lower is not None:
            extents.append(vertical.Extent(part.lower, part.upper))
            if part.simplified:
                notes.append("En kropp som inte är ett lodrätt prisma förenklades till ett: ytan i botten och höjderna behölls.")
        elif part.height is not None and limit in (vertical.UPWARD, vertical.DOWNWARD):
            extents.append(vertical.Extent(None, part.height) if limit == vertical.UPWARD
                           else vertical.Extent(part.height, None))
        else:
            if part.height is not None:
                notes.append("Ett höjdvärde utan vertikal avgränsning ignorerades (det går inte att se åt vilket håll "
                             "bestämmelsen gäller).")
            extents.append(vertical.Extent())
    extent = vertical.hull(extents) if extents else vertical.Extent()
    if len({(e.lower, e.upper) for e in extents}) > 1:
        notes.append("Delarna av en bestämmelse har olika höjd: den gäller nu över hela spannet.")
    return build_geometry(descriptions), extent, notes


# -- planbestämmelseobjekt ----------------------------------------------------------------------
def _provision(properties: dict, extent: Optional[vertical.Extent] = None) -> ImportedProvision:
    motiv = ((properties.get("planbestammelsebeskrivning") or {}).get("motiv") or "").strip() or None
    extent = extent or vertical.Extent()
    limit = properties.get("vertikalAvgransning")
    return ImportedProvision(
        extent=extent,
        # en avgränsning utan höjd sparas som den är; med höjd härleds den ur höjden, och en kropp får ingen
        vertikal_avgransning=limit if not extent.limited and limit in (vertical.UPWARD, vertical.DOWNWARD) else None,
        catalog_id=properties.get("planbestammelsekatalogreferens") or "",
        formulering=properties.get("bestammelseformulering") or "",
        values=[v for v in properties.get("bestammelsevarde") or [] if isinstance(v, dict)],
        motiv=motiv,
        giltighetstid=properties.get("giltighetstid"),
        borjar_galla_efter=properties.get("borjarGallaEfter"),
    )


def _table(properties: dict, descriptions: list[dict]) -> Optional[str]:
    is_use = properties.get("feature:typ") == USE_TYPE
    if is_use:
        return cat.USE_LAYER
    kind = ((descriptions or [{}])[0].get("geometri") or {}).get("typ")
    return {"yta": "egenskap_yta", "multiyta": "egenskap_yta", "kropp": "egenskap_yta", "linje": "egenskap_linje",
            "multilinje": "egenskap_linje", "punkt": "egenskap_punkt", "multipunkt": "egenskap_punkt"}.get(kind)


# -- olika värden på samma mark ------------------------------------------------------------------
AREA_TABLES = (cat.USE_LAYER, "egenskap_yta")
OVERLAP_TOLERANCE_M2 = 1.0  # mindre överlapp än så är grannytor som delar en gräns


@dataclass
class _Placed:
    """En bestämmelse med sin yta, så som den står i leveransen."""
    properties: dict
    geometry: QgsGeometry
    extent: vertical.Extent


def _describe(properties: dict) -> str:
    """Bestämmelsen i en varning: formuleringen (kortad) och objektets identitet, så att den går att hitta i källan."""
    text = (properties.get("bestammelseformulering") or "utan formulering").strip()
    text = text if len(text) <= 70 else text[:67].rstrip() + "…"
    identity = str(properties.get("objektidentitet") or "")[:8]
    return f"”{text}”" + (f" (objekt {identity})" if identity else "")


def _values_of(properties: dict) -> tuple[tuple, tuple]:
    """(textvärdena, talen) i bestämmelsevärdet. Textvärdena säger vad som regleras (huvudbyggnad eller komplementbyggnad),
    talen hur mycket."""
    texts, numbers = [], []
    for value in properties.get("bestammelsevarde") or []:
        if not isinstance(value, dict):
            continue
        name, text = str(value.get("beskrivning") or ""), str(value.get("variabelvarde") or "").strip()
        if value.get("datatyp") == "decimaltal":
            number = bm.normalize_decimal(text)
            numbers.append((name, float(number) if number is not None else text, str(value.get("enhet") or "")))
        else:
            texts.append((name, text))
    return tuple(texts), tuple(numbers)


def _share_height(a: vertical.Extent, b: vertical.Extent) -> bool:
    """Om två höjdavgränsningar har något gemensamt (en utan avgränsning har det med allt)."""
    below = a.upper is not None and b.lower is not None and a.upper <= b.lower
    above = b.upper is not None and a.lower is not None and b.upper <= a.lower
    return not (below or above)


def conflicting_values(placed: list) -> list[str]:
    """Varningar för bestämmelser av samma slag som anger olika värden på samma mark, till exempel byggnadsarea 25 % och
    30 %: samma katalogreferens och samma textvärden men olika tal, ytor som överlappar (mer än
    ``OVERLAP_TOLERANCE_M2``) och höjder som möts. Oftast är en yta fel i källan. En varning per par av värden, med den
    sammanlagda överlappningen."""
    groups: dict[tuple, list] = {}
    for item in placed:
        texts, numbers = _values_of(item.properties)
        if numbers:
            key = (item.properties.get("planbestammelsekatalogreferens"), texts)
            groups.setdefault(key, []).append((numbers, item))
    found: dict[tuple, list] = {}  # (grupp, värdepar) -> [sammanlagd area, den ena, den andra]
    for key, members in groups.items():
        for i, (first_numbers, first) in enumerate(members):
            for second_numbers, second in members[i + 1:]:
                if first_numbers == second_numbers or not _share_height(first.extent, second.extent):
                    continue
                if not first.geometry.boundingBox().intersects(second.geometry.boundingBox()):
                    continue
                area = first.geometry.intersection(second.geometry).area()
                if area <= OVERLAP_TOLERANCE_M2:
                    continue
                pair = (key, frozenset((first_numbers, second_numbers)))
                entry = found.setdefault(pair, [0.0, first, second])
                entry[0] += area
    return [f"Olika värden gäller samma mark ({area:.0f} m²): {_describe(first.properties)} och "
            f"{_describe(second.properties)}. Kontrollera ytorna i källan." for area, first, second in found.values()]


# -- beslut och dokument ------------------------------------------------------------------------
def _decision(info: dict) -> dict:
    """En rad i ``beslutsinformation``, ur ett ``beslutsinformation``-objekt (se ``export_ngp.decision_info``)."""
    values: dict[str, Any] = {}
    for key in ("instansInomKommunen", "diarienummerKommun", "diarienummerFullmaktige", "beslutstyp",
                "arkividentitetKommun", "datumPaborjat", "datumAntagande", "genomforandetidStartar"):
        values[key] = info.get(key)
    values["genomforandetid"] = info.get("genomforandetid")
    values["datumLagakraft"] = "; ".join(info.get("datumLagakraft") or []) or None
    values["foregaendePlansBeteckning"] = "; ".join(info.get("foregaendePlansBeteckning") or []) or None
    values["berordDomsMalnummer"] = "; ".join(info.get("berordDomsMalnummer") or []) or None
    return values


def _document_reference(reference: dict) -> dict:
    date_event = reference.get("datum") or {}
    links = reference.get("referens") or []
    link = links[0] if links else {}
    return {
        "namn": reference.get("namn"),
        "kortnamn": reference.get("kortnamn"),
        "datum": date_event.get("datum"),
        "handelse": date_event.get("handelse"),
        "lank": link.get("lank"),
        "referensIdentitet": link.get("identitet"),
        "specifikReferens": "; ".join(reference.get("specifikReferens") or []) or None,
    }


def _documents(properties: dict) -> list[dict]:
    documents: list[dict] = []
    description = (properties.get("planbeskrivning") or {}).get("planbeskrivning")
    if description:
        documents.append({"roll": "planbeskrivning", **_document_reference(description)})
    for beslut in properties.get("beslutsinformation") or []:
        for handling in beslut.get("beslutshandling") or []:
            reference = handling.get("dokument") or {}
            documents.append({"roll": "beslutshandling", "innehall": "; ".join(handling.get("innehall") or []) or None,
                              **_document_reference(reference)})
    for underlag in properties.get("planeringsunderlag") or []:
        reference = underlag.get("underlag") or {}
        documents.append({"roll": "planeringsunderlag", "huvudomrade": underlag.get("huvudomrade"),
                          "underlagstyp": underlag.get("underlagstyp"), **_document_reference(reference)})
    return documents


# -- hela leveransen ----------------------------------------------------------------------------
def parse(collection: dict) -> ImportedPlan:
    """Tolkar en ``FeatureCollection`` (se ``export_ngp.export_plan``). Kastar ``ImportError_`` om den inte ser ut
    som en leverans av en detaljplan."""
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ImportError_("Filen är inte en FeatureCollection.")
    features = collection.get("features") or []
    plan_feature = next((f for f in features if f.get("properties", {}).get("feature:typ") == "detaljplan"), None)
    if plan_feature is None:
        raise ImportError_("Filen innehåller ingen detaljplan (feature:typ = detaljplan saknas).")
    attrs = plan_feature["properties"]
    quality = attrs.get("kvalitetsbeskrivning") or {}
    plan = ImportedPlan(
        attrs={
            "kommun": attrs.get("kommun"), "beteckning": attrs.get("beteckning"), "namn": attrs.get("namn"),
            "syfte": attrs.get("syfte"), "status": attrs.get("status"), "typ": attrs.get("typ"),
            "vertikalAvgransning": attrs.get("vertikalAvgransning"),
            "digitaliseringsniva": quality.get("digitaliseringsniva"), "beskrivningNiva": quality.get("beskrivningNiva"),
            "korrigeradeGranser": quality.get("korrigeradeGranser"),
            "kontrolleratPlaneringsunderlag": quality.get("kontrolleratPlaneringsunderlag"),
            "anvandbarhet": attrs.get("anvandbarhet"), "beskrivningAnvandbarhet": attrs.get("beskrivningAnvandbarhet"),
        },
        geometry=build_geometry(attrs.get("plangeometri")),
        documents=_documents(attrs),
    )
    decisions = attrs.get("beslutsinformation") or []
    if decisions:
        plan.decision = _decision(decisions[0])
        if len(decisions) > 1:
            plan.warnings.append(f"Planen har {len(decisions)} beslut i leveransen; bara det första importeras "
                                 "(en rad kan redigeras här).")
    if plan.geometry is None or plan.geometry.isEmpty():
        raise ImportError_("Detaljplanen saknar en giltig plangeometri.")

    grouped: dict[tuple, ImportedArea] = {}
    order: list[tuple] = []
    placed: list[_Placed] = []  # ytorna, för kontrollen av olika värden på samma mark
    for feature in features:
        properties = feature.get("properties") or {}
        if properties.get("feature:typ") not in (USE_TYPE, PROPERTY_TYPE):
            continue
        descriptions = properties.get("bestammelsegeometri") or []
        table = _table(properties, descriptions)
        geometry, extent, notes = build_area(descriptions, properties.get("vertikalAvgransning"))
        if table is None or geometry is None or geometry.isEmpty():
            kinds = ", ".join(sorted({str((d.get("geometri") or {}).get("typ") or "okänd") for d in descriptions
                                      if isinstance(d, dict)})) or "saknas"
            plan.warnings.append(f"Bestämmelsen {_describe(properties)} har en geometri som pluginet inte kan läsa "
                                 f"(typ: {kinds}) och hoppades över.")
            continue
        if table in AREA_TABLES:
            placed.append(_Placed(properties, geometry, extent))
        plan.warnings += [note for note in notes if note not in plan.warnings]
        key = (table, geometry.asWkt(3))  # ytan i planet: bestämmelser med olika höjd delar yta, höjden ligger på raden
        if key not in grouped:
            grouped[key] = ImportedArea(table=table, geometry=geometry)
            order.append(key)
        area = grouped[key]
        if table == "egenskap_yta" and properties.get("sekundarEgenskapsgrans"):
            area.sekundar = True
        area.provisions.append(_provision(properties, extent))
    plan.areas = [grouped[key] for key in order]
    plan.warnings += conflicting_values(placed)
    return plan
