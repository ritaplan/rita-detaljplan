"""Planmosaikens utseende på ett ställe: mått för gränslinjer och mönster vid olika kartskalor.

Mått anges i pixlar vid referensskalan 1:1000 (som i Rita Detaljplan, där de är punkter vid samma skala) och skalas med
kartskalan: zoomar man ut blir linjer och mönster proportionellt mindre, i stället för att ligga kvar i samma pixelbredd
och täcka planen. Två saker skiljer från en plankarta på papper, eftersom skärmen har en minsta pixelstorlek:

  * en linje blir aldrig smalare än sin minsta bredd, och streckmönstret byts mot en heldragen linje när luckorna blir
    för små för att synas
  * gränser och mönster som blivit för små för att synas ritas inte alls (användnings- och egenskapsgränser, mönster)

Skalan delas i band (``BAND_EDGES``); alla mått i ett band räknas för bandets mitt, så att alla tjänster ritar likadant.
GeoServers stilar (``geoserver/bygg_stilar.py``) och QGIS-projektet (``qgis/skapa_qgis_projekt.py``) bygger på det här
direkt. Origo-stilen (``web/html/planmosaik.js``) har samma tal i en tabell: ändra båda när något ändras här.
"""
from __future__ import annotations

REFERENCE_SCALE = 1000
BAND_EDGES = (1500, 3000, 6000, 12000, 24000, 48000)  # kartskalans nämnare där ett band slutar och nästa börjar
MAX_ENLARGE = 2.0  # zoomar man in förbi referensskalan växer måtten högst så mycket
MIN_VISIBLE_GAP = 1.2  # pixlar: mindre luckor i ett streckmönster syns inte, linjen ritas då heldragen
MIN_PATTERN_FACTOR = 0.3  # mönster ritas inte när de skulle bli mindre än så, jämfört med referensskalan
MIN_PATTERN_GAP = 4.5  # pixlar: minsta mellanrum mellan markörer, annars blir mönstret en mörk yta

# Gränslinjer. Streckmönstrets rytm är Boverkets (BFS 2020:6), men bredden och längderna är större än på papper: på en
# skärm syns en tunn linje knappt, och mönstret ska fortfarande synas som streck. Pixlar vid referensskalan.
# max_scale: ritas bara i band som börjar före den här skalan (nämnaren), None = alltid
LINES = {
    "egenskapsgrans": {"width": 2.2, "dash": (14, 6, 3, 6, 3, 6), "min_width": 0.9, "max_scale": 6000},
    "anvandningsgrans": {"width": 3.6, "dash": (14, 3, 2, 3), "min_width": 1.2, "max_scale": 12000},
    "planomradesgrans": {"width": 5.5, "dash": (22, 5, 6, 5, 22, 5), "min_width": 1.8, "max_scale": None},
}
# Mönster för egenskapsytor. size = markörens storlek, margin = mellanrum, båda i pixlar vid referensskalan.
PATTERNS = {
    "prickmark": {"shape": "circle", "size": 1.6, "margin": 5.5},
    "korsmark": {"shape": "cross", "size": 4.5, "margin": 8.0, "stroke": 0.3},
    "ringprickad": {"shape": "ring", "size": 4.0, "margin": 8.0, "stroke": 0.6},
}


def bands() -> list[tuple[int, int | None, float]]:
    """Banden som (från, till, skala måtten räknas för). ``till`` är None för det sista bandet (obegränsat)."""
    edges = [0, *BAND_EDGES]
    result = []
    for index, lower in enumerate(edges):
        upper = edges[index + 1] if index + 1 < len(edges) else None
        if upper is None:
            representative = lower * 1.5
        elif lower == 0:
            representative = float(REFERENCE_SCALE)
        else:
            representative = (lower * upper) ** 0.5
        result.append((lower, upper, representative))
    return result


def factor(scale: float) -> float:
    return min(MAX_ENLARGE, REFERENCE_SCALE / scale)


def line_style(kind: str, lower: int, scale: float) -> dict | None:
    """Bredd (px) och streckmönster (px, eller None = heldragen) för en gränslinje i ett band, eller None om den inte ritas."""
    spec = LINES[kind]
    if spec["max_scale"] is not None and lower >= spec["max_scale"]:
        return None
    scale_factor = factor(scale)
    dash = [value * scale_factor for value in spec["dash"]]
    if min(dash[1::2]) < MIN_VISIBLE_GAP:
        dash = None
    return {"width": round(max(spec["min_width"], spec["width"] * scale_factor), 2),
            "dash": [round(value, 2) for value in dash] if dash else None}


def pattern_style(kind: str, scale: float) -> dict | None:
    """Storlek, period (avstånd mellan markörer) och linjebredd (px) för ett mönster, eller None om det blivit för litet."""
    scale_factor = factor(scale)
    if scale_factor < MIN_PATTERN_FACTOR:
        return None
    spec = PATTERNS[kind]
    size = max(1.2, spec["size"] * scale_factor)
    period = max(size + MIN_PATTERN_GAP, (spec["size"] + spec["margin"]) * scale_factor)
    return {"shape": spec["shape"], "size": round(size, 2), "period": round(period, 2),
            "stroke": round(max(0.3, spec.get("stroke", 0) * scale_factor), 2)}
