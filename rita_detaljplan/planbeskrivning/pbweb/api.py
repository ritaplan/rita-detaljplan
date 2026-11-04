"""Gränssnittet mellan webbsidan och programmets kärna.

Webbsidan (JavaScript) anropar metoderna i ``Webb`` och ritar upp det som ``tillstand()`` ger tillbaka. Allt som går in och ut
är vanliga värden (text, tal, listor, ordböcker) som kan skickas som JSON; fel kommer som ``{"fel": "text"}`` i stället för
som undantag, så att sidan kan visa dem. Filerna ligger i webbläsarens minne: sökvägarna är sökvägar i Pyodides virtuella
filsystem. Ingenting skickas någonstans.

Logiken är sessionens (``pbapp/session.py``), samma som i fönstret: den här filen väljer bara vad som visas och ger
åtgärderna enkla namn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..pbapp import session as ss
from ..pbkarna import geometri as geo
from ..pbkarna import planbeskrivning as pb
from ..pbkarna import planbeskrivning_check as ck
from ..pbkarna import planbeskrivning_docx as dx
from ..pbkarna import plankarta as pk

MAX_TEXT = 420  # tecken av ett avsnitts eller ett motivs text som skickas till sidan (hela texten behövs inte där)
QGIS_PROJEKT = (".qgz", ".qgs")


def _kort(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT].rstrip() + "…"


def _fel(exc: Exception) -> dict:
    return {"fel": str(exc) or exc.__class__.__name__}


def karta_svg(karta: Optional[geo.Karta], markera=()) -> str:
    """Planområdet och ytorna som SVG. Ytorna i ``markera`` (identiteter) får klassen ``mark``; användningsytor ``anv``,
    övriga ``egen``. Färgerna sätter webbsidan med CSS. Tom text om planen saknar geometri."""
    bounds = karta.bounds() if karta else None
    if not bounds:
        return ""
    x0, y0, x1, y1 = bounds
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    mark = set(markera or ())

    def punkter(part) -> str:
        return " ".join(f"{x - x0:.1f},{y1 - y:.1f}" for x, y in part)

    def form(shape: geo.Shape, klass: str) -> str:
        d = " ".join("M" + punkter(p) + ("Z" if shape.closed else "") for p in shape.parts if p)
        return f'<path class="{klass}" d="{d}" fill-rule="evenodd" vector-effect="non-scaling-stroke"/>'

    delar = []
    if karta.border:
        delar.append(form(karta.border, "grans"))
    ordning = sorted(karta.areas.items(), key=lambda kv: (karta.layer_of.get(kv[0]) != "anvandning_yta", kv[0] in mark))
    for ident, shape in ordning:
        klass = "anv" if karta.layer_of.get(ident) == "anvandning_yta" else "egen"
        delar.append(form(shape, klass + (" mark" if ident in mark else "")))
    m = max(w, h) * 0.03
    return (f'<svg viewBox="{-m:.1f} {-m:.1f} {w + 2 * m:.1f} {h + 2 * m:.1f}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Plankartan">' + "".join(delar) + "</svg>")


class Webb:
    """En session för webbsidan: en plankarta, en planbeskrivning och de val användaren gör."""

    def __init__(self, store: Optional[ss.Store] = None):
        self.s = ss.Session(store or ss.Store.memory())
        self.docx_namn = ""

    # -- filer -------------------------------------------------------------------------------------
    def las_plankarta(self, sokvag: str) -> dict:
        path = Path(sokvag)
        if path.suffix.lower() in QGIS_PROJEKT:
            return {"fel": "Ett QGIS-projekt pekar på filer på din dator som webbläsaren inte kommer åt. Välj planens "
                           "GeoPackage (.gpkg) eller en JSON-leverans (.json) i stället."}
        try:
            self.s.load_plankarta(path)
        except (ss.SessionError, pk.PlankartaError) as exc:
            return _fel(exc)
        except Exception as exc:  # en trasig eller främmande fil ska ge ett fel på sidan, inte stoppa den
            return {"fel": f"Plankartan kunde inte läsas: {exc}"}
        return {"ok": True}

    def las_planbeskrivning(self, sokvag: str) -> dict:
        path = Path(sokvag)
        self.docx_namn = path.name
        try:
            self.s.load_docx(path)
        except ss.SessionError as exc:
            return _fel(exc)
        except Exception as exc:
            return {"fel": f"Planbeskrivningen kunde inte läsas: {exc}"}
        return {"ok": True}

    def valj_plan(self, index: int) -> dict:
        """Väljer plan när plankartan innehåller flera."""
        try:
            self.s.choose_plan(int(index))
        except (IndexError, ss.SessionError) as exc:
            return _fel(exc)
        return {"ok": True}

    # -- åtgärder ----------------------------------------------------------------------------------
    def _avsnitt(self, nyckel: str) -> Optional[dx.Avsnitt]:
        a = self.s.analysis
        return next((x for x in a.sections if self.s.key(x) == nyckel), None) if a else None

    def _motiv(self, signatur: str) -> Optional[dx.Motiv]:
        a = self.s.analysis
        return next((m for m in a.motives if self.s.signature(m) == signatur), None) if a else None

    def valj_indelning(self, nyckel: str, tema: str, grupp: str, undergrupp: str) -> dict:
        section = self._avsnitt(nyckel)
        if section is None:
            return {"fel": "Avsnittet finns inte längre."}
        self.s.set_indelning(section, tema, grupp, undergrupp)
        return {"ok": True}

    def godkann(self, nyckel: str) -> dict:
        section = self._avsnitt(nyckel)
        if section is None:
            return {"fel": "Avsnittet finns inte längre."}
        self.s.approve(section)
        return {"ok": True}

    def hoppa_over(self, nyckel: str, hoppa: bool = True) -> dict:
        section = self._avsnitt(nyckel)
        if section is None:
            return {"fel": "Avsnittet finns inte längre."}
        self.s.skip(section, bool(hoppa))
        return {"ok": True}

    def vaxla_motiv_avsnitt(self, nyckel: str) -> dict:
        """Pekar ut avsnittet som motiv till bestämmelser, eller ångrar det (räknar om analysen)."""
        section = self._avsnitt(nyckel)
        if section is None:
            return {"fel": "Avsnittet finns inte längre."}
        return {"ok": True, "paa": self.s.toggle_motive_host(section)}

    def koppla_motiv(self, signatur: str, bestammelse: Optional[str]) -> dict:
        """Kopplar motivet till bestämmelsen (dess ``nyckel`` ur ``tillstand``), eller tar bort kopplingen (None)."""
        motive = self._motiv(signatur)
        if motive is None:
            return {"fel": "Motivet finns inte längre."}
        key = None
        if bestammelse:
            key = next((p.key for p in self.s.provisions if p.refs and pk.key_text(p.key) == bestammelse), None)
            if key is None:
                return {"fel": "Bestämmelsen finns inte i planen."}
        self.s.link(motive, key)
        return {"ok": True}

    # -- filer ut ----------------------------------------------------------------------------------
    def standardnamn(self, suffix: str, filandelse: str = ".docx") -> str:
        stem = Path(self.docx_namn).stem if self.docx_namn else "planbeskrivning"
        return stem + suffix + filandelse

    def spara_kopia(self, sokvag: str, granskning: bool = False) -> dict:
        """Skriver leveranskopian (eller granskningskopian med en kommentar per avsnitt) till ``sokvag``."""
        try:
            r = self.s.write_copy(sokvag, review=bool(granskning))
        except ss.SessionError as exc:
            return _fel(exc)
        return {"ok": True, "avsnitt": r.avsnitt, "motiv": r.motiv, "kommentarer": r.kommentarer}

    def oversikt_csv(self) -> dict:
        """Översikten över taggarna som semikolonavgränsad text (Excel i Sverige öppnar den direkt)."""
        if self.s.analysis is None:
            return {"fel": "Välj planbeskrivningen först."}
        return {"ok": True, "text": dx.overview_csv(dx.overview(self.s.analysis))}

    def karta(self, bestammelse: Optional[str] = None) -> str:
        """Kartan som SVG, med ytorna för en bestämmelse (dess ``nyckel``) markerade."""
        plan = self.s.plan
        markera: list = []
        if plan is not None and bestammelse:
            key = next((p.key for p in plan.provisions if pk.key_text(p.key) == bestammelse), None)
            markera = plan.areas.get(key, []) if key is not None else []
        return karta_svg(self.s.karta, markera)

    # -- det sidan ritar ---------------------------------------------------------------------------
    @staticmethod
    def alternativ() -> dict:
        """Tema, grupper och undergrupper som kan väljas: {tema: {grupp: [undergrupp, …]}}."""
        return {tema: {grupp: pb.undergrupper(tema, grupp) for grupp in pb.grupper(tema)} for tema in pb.temas()}

    def tillstand(self) -> dict:
        s = self.s
        plan = s.plan
        ut: dict = {"plan": None, "dokument": None, "klar": s.ready and plan is not None}
        if plan is not None:
            ut["plan"] = {
                "rubrik": plan.rubrik, "namn": plan.namn, "beteckning": plan.beteckning, "syfte": plan.syfte,
                "bestammelser": len(plan.provisions), "objekt": sum(len(p.refs) for p in plan.provisions),
                "ytor": len(s.karta.areas) if s.karta else 0, "karta": karta_svg(s.karta),
                "planer": [{"index": i, "rubrik": p.rubrik} for i, p in enumerate(s.plans)],
                "vald": s.plans.index(plan) if plan in s.plans else 0,
            }
        a = s.analysis
        if a is not None:
            ut["dokument"] = {"namn": self.docx_namn, "avsnitt": len(a.sections), "motiv": len(a.motives)}
        if not ut["klar"]:
            return ut

        ut["raknare"] = {status: antal for status, antal in s.counts().items() if status not in (ss.RUBRIK, ss.MOTIV)}
        ut["status_text"] = {k: v for k, v in ss.STATUS_TEXT.items() if k not in (ss.RUBRIK, ss.MOTIV)}
        ut["avsnitt"] = []
        for section in s.tagged_sections():
            i = section.indelning
            ut["avsnitt"].append({
                "nyckel": s.key(section), "sokvag": list(section.path), "rubrik": section.path[-1],
                "status": s.status(section), "varfor": s.why(section),
                "tema": i.tema or "", "grupp": i.grupp or "", "undergrupp": i.undergrupp or "",
                "text": _kort(section.text), "motivtraffar": s.motive_hits(section), "ar_motiv": s.hosts_motive(section),
                "lage": [pk.key_text(k) for k in section.lage_keys],
            })
        ut["motiv"] = []
        for motive in a.motives:
            provision = s.provision(motive.key)
            ut["motiv"].append({
                "signatur": s.signature(motive), "beteckning": motive.label, "rubrik": motive.title, "text": _kort(motive.text),
                "sokvag": list(motive.path), "status": s.motive_status(motive),
                "bestammelse": pk.key_text(provision.key) if provision else None,
            })
        linked = {m.key for m in a.motives}
        ut["bestammelser"] = [{
            "nyckel": pk.key_text(p.key), "beteckning": p.label, "text": p.text, "slag": pk.KIND_NAMES.get(plan.kinds.get(p.key), ""),
            "tekniskt": p.technical, "objekt": len(p.refs), "har_motiv": p.key in linked,
        } for p in plan.provisions if p.refs]
        found = s.findings()
        errors, warnings = ck.counts(found)
        ut["fynd"] = [{"allvarlighet": f.allvarlighet, "text": f.text, "var": f.var, "krav": f.krav, "symbol": f.symbol}
                      for f in sorted(found, key=lambda f: ck.ORDNING[f.allvarlighet])]
        ut["fel"], ut["varningar"] = errors, warnings
        ut["namn"] = {"leverans": self.standardnamn("_leverans"), "granskning": self.standardnamn("_granskning"),
                      "oversikt": self.standardnamn("_taggar", ".csv")}
        return ut
