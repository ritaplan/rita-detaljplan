"""Kontroll av en färdig plankarta som PDF: kan Acrobat spara sidan som bild, är kartan vektorgrafik, och vad återstår för
PDF/A. Ren Python (ingen QGIS), så att den kan provas utan QGIS.

Det som kontrolleras är det vi sett stoppa eller förvåna i praktiken:

* **Strecksatser** (operatorn ``d``). QGIS skriver ett streckmönster som är anpassat till linjens längd som en lång sats
  (tiotals tal, ofta med en sista lucka på 0,0001) och Acrobat vägrar då spara sidan som bild ("Streckargument är
  ogiltiga"). Satser med högst 6 tal godtogs i en riktig plankarta; längre satser och luckor nära noll flaggas.
* **Bild i stället för vektor.** Kartan blir en stor bild när något i den har ett blandningsläge (Multiplicera) och
  vektorutskrift inte valts.
* **PDF/A, georeferens och genomskinlighet**, som en konverterare till PDF/A får hantera (PDF/A-1 tillåter varken
  genomskinlighet eller de utökningar en georeferens ger).
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import archive

MAX_DASH_NUMBERS = 6  # som mest så här många tal i en strecksats godtogs av Acrobat (se ovan)
MIN_DASH_PART = 0.05  # kortare streck eller luckor än så (i punkter) flaggas
BIG_IMAGE_PIXELS = 1_500_000  # en bild som är större än så räknas som att kartan är en bild

FEL, VARNING, INFO = "fel", "varning", "info"

_DASH = re.compile(rb"\[([^\]]*)\]\s*([\-\d.eE+]+)\s*d(?![A-Za-z])")
_STREAM = re.compile(rb"stream\r?\n")
_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
_MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*([\-\d.]+)\s+([\-\d.]+)\s+([\-\d.]+)\s+([\-\d.]+)\s*\]")
_IMAGE = re.compile(rb"/Subtype\s*/Image")
_WIDTH, _HEIGHT = re.compile(rb"/Width\s+(\d+)"), re.compile(rb"/Height\s+(\d+)")
_ALPHA = re.compile(rb"/(?:ca|CA)\s+([\d.]+)")


@dataclass
class Finding:
    level: str
    text: str


@dataclass
class PdfReport:
    path: Path
    size_bytes: int = 0
    pages: int = 0
    size_mm: Optional[tuple[int, int]] = None
    images: int = 0
    big_images: int = 0
    dash_arrays: int = 0
    longest_dash: int = 0
    georeferenced: bool = False
    pdfa: Optional[str] = None
    findings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Ingenting som stoppar: inga fel (varningar och info får finnas)."""
        return not any(f.level == FEL for f in self.findings)

    @property
    def vector(self) -> bool:
        return self.big_images == 0

    def summary(self) -> str:
        """En rad om vad filen är."""
        size = f"{self.size_mm[0]} × {self.size_mm[1]} mm" if self.size_mm else "okänd storlek"
        kind = "vektorgrafik" if self.vector else "kartan är en bild"
        pages = "1 sida" if self.pages == 1 else f"{self.pages} sidor"
        return f"{self.path.name}: {kind}, {size}, {pages}, {self.size_bytes / 1024:.0f} KB."

    def text(self) -> str:
        lines = [self.summary()]
        for finding in self.findings:
            lines.append(f"{finding.level.upper()}: {finding.text}")
        return "\n".join(lines)


def dash_arrays(data: bytes) -> list[list[float]]:
    """Alla strecksatser (utan de tomma, som betyder heldragen linje) i innehållsströmmarna."""
    found = []
    for match in _STREAM.finditer(data):
        end = data.find(b"endstream", match.end())
        try:
            text = zlib.decompress(data[match.end():end])
        except zlib.error:
            continue
        for item in _DASH.finditer(text):
            numbers = item.group(1).split()
            try:
                values = [float(v) for v in numbers]
            except ValueError:
                continue
            if values:
                found.append(values)
    return found


def check_pdf(path: Path) -> PdfReport:
    """Läser PDF:en och returnerar vad som hittades, med fynd i klartext."""
    path = Path(path)
    data = path.read_bytes()
    report = PdfReport(path=path, size_bytes=len(data))
    report.pages = len(_PAGE.findall(data))
    box = _MEDIABOX.search(data)
    if box:
        x0, y0, x1, y1 = (float(v) for v in box.groups())
        report.size_mm = (round((x1 - x0) * 25.4 / 72), round((y1 - y0) * 25.4 / 72))
    for image in _IMAGE.finditer(data):
        window = data[max(0, image.start() - 400):image.end() + 400]
        width, height = _WIDTH.search(window), _HEIGHT.search(window)
        report.images += 1
        if width and height and int(width.group(1)) * int(height.group(1)) >= BIG_IMAGE_PIXELS:
            report.big_images += 1
    report.georeferenced = b"/VP" in data and b"/Measure" in data
    arrays = dash_arrays(data)
    report.dash_arrays = len(arrays)
    report.longest_dash = max((len(a) for a in arrays), default=0)

    findings = report.findings
    too_long = [a for a in arrays if len(a) > MAX_DASH_NUMBERS]
    too_small = [a for a in arrays if min(a) < MIN_DASH_PART]
    if too_long or too_small:
        findings.append(Finding(FEL, "PDF:en har strecksatser som Acrobat vägrar spara som bild (felet \"Streckargument är "
                                f"ogiltiga\"): {len(too_long)} med fler än {MAX_DASH_NUMBERS} tal och {len(too_small)} med "
                                "värden nära noll. Ritades teckenförklaringen eller kartan med ett äldre plugin? "
                                "Öppna planen i den nya versionen och exportera igen."))
    if report.big_images:
        findings.append(Finding(VARNING, "Kartan är en bild och inte vektorgrafik (något i den har ett blandningsläge, "
                                         "eller vektorutskrift är inte vald). Då går inte vektorerna att återskapa i en "
                                         "PDF/A-konvertering."))
    alphas = {float(a) for a in _ALPHA.findall(data) if a.replace(b".", b"").isdigit()}
    if any(a < 1.0 for a in alphas) or b"/SMask" in data:
        findings.append(Finding(INFO, "Filen innehåller genomskinlighet. PDF/A-1 tillåter det inte (en konverterare plattar ut "
                                      "det); PDF/A-2 och 3 tillåter det."))
    if report.georeferenced:
        findings.append(Finding(INFO, "Filen är georefererad. En strikt PDF/A-1-kontroll kan anmärka på det; PDF/A-2 och 3 är "
                                      "mer förlåtande."))
    name, version, _ = archive.sniff_format(path)
    if name == "PDF/A":
        report.pdfa = version
        findings.append(Finding(INFO, f"Filen säger sig vara PDF/A ({version})."))
    else:
        findings.append(Finding(INFO, "Filen är inte PDF/A. Konvertera den (till exempel i Acrobat, helst till PDF/A-2b) och "
                                      "kontrollera resultatet med en PDF/A-validerare som veraPDF."))
    return report
