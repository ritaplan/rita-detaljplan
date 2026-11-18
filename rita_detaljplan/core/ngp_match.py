"""Hittar en plan i NGP när dess objektidentitet inte finns där: planer som levererats av ett annat program, eller vars
planområde fått ett nytt id i QGIS, ligger under ett annat id men har samma beteckning, namn och datum för laga kraft.

Ren logik utan QGIS och nätverk. Ett svar härifrån är en *trolig* träff, aldrig en säker: det bygger på att uppgifterna
liknar varandra, inte på att id:n är lika."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .ngp_client import PlanHit

MIN_SCORE = 4  # beteckning + datum (5), beteckning + namn (4–5) eller datum + likt namn (4)
SIMILAR = 0.85  # så lika ska namnen vara för att räknas som samma
LIKE = 0.7


def _key(text: str) -> str:
    """Bokstäver och siffror i gemener: 'Kv. Norr 1-23' och 'kv norr 1 23' är samma sak."""
    return re.sub(r"[\W_]+", "", (text or "").casefold())


def _day(text: str) -> str:
    return (text or "").strip()[:10]


def kommun_key(name: str) -> str:
    """Kommunnamn som kan jämföras: 'Lidköpings kommun' och 'Lidköping' blir samma."""
    text = re.sub(r"\s+kommun\s*$", "", (name or "").strip().casefold())
    text = re.sub(r"\s+", " ", text)
    return text[:-1] if text.endswith("s") else text


def collection_for(kommun: str, collections: dict[str, str]) -> Optional[str]:
    """Datamängden (kommunkoden) i NGP för en kommun, utifrån kommunens namn eller kod i planen. ``collections`` är
    kommunkod -> kommunnamn, som Sök-API:et anger dem."""
    kommun = (kommun or "").strip()
    if kommun in collections:
        return kommun
    wanted = kommun_key(kommun)
    if not wanted:
        return None
    found = [code for code, name in collections.items() if kommun_key(name) == wanted]
    return found[0] if len(found) == 1 else None


def match_plan(namn: str, beteckning: str, laga_kraft: str, candidates: Iterable[PlanHit]) -> tuple[Optional[PlanHit], str]:
    """Den kandidat i NGP som troligast är planen, med skälen i klartext, eller (None, "") om ingen är tillräckligt lik eller
    om flera är lika bra. Beteckning och datum för laga kraft ska vara lika; namnet får vara ungefär lika."""
    want_beteckning, want_day, want_namn = _key(beteckning), _day(laga_kraft), _key(namn)
    scored: list[tuple[int, PlanHit, list[str]]] = []
    for hit in candidates:
        score, reasons = 0, []
        if want_beteckning and _key(hit.beteckning) == want_beteckning:
            score += 3
            reasons.append("samma beteckning")
        if want_day and _day(hit.datum_lagakraft) == want_day:
            score += 2
            reasons.append("samma datum för laga kraft")
        if score and want_namn and _key(hit.namn):  # namnet jämförs bara när något annat redan stämmer
            ratio = SequenceMatcher(None, want_namn, _key(hit.namn)).ratio()
            if ratio >= SIMILAR:
                score += 2
                reasons.append("samma namn" if ratio >= 0.999 else f"likt namn ({round(ratio * 100)} %)")
            elif ratio >= LIKE:
                score += 1
                reasons.append(f"ungefär likt namn ({round(ratio * 100)} %)")
        if score >= MIN_SCORE:
            scored.append((score, hit, reasons))
    if not scored:
        return None, ""
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1].objektidentitet != scored[0][1].objektidentitet:
        return None, ""  # flera lika bra träffar: bättre att inte gissa
    return scored[0][1], ", ".join(scored[0][2])
