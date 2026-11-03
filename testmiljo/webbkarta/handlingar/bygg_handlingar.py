"""Gör testhandlingar (PDF) till demoplanerna, så att informationsrutan i webbkartan har något att länka till.

    python-qgis.bat testmiljo/webbkarta/handlingar/bygg_handlingar.py <planbeskrivning.docx> <utmapp>

Skriver <utmapp>/<plan-id>/planbeskrivning.pdf och dagvattenutredning.pdf för demoplanerna. Texten i planbeskrivningen är
demoplanens egen. Plankartorna (plankarta.pdf) görs på servern av bygg_plankartor.py ur samma karta som visas i webbkartan.
Det här är testhandlingar: riktiga handlingar läggs ut av kommunen och länkas i tabellen dokument.
"""
import html
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from qgis.PyQt.QtCore import QMarginsF
from qgis.PyQt.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

PLANER = {"demo_dp_01": "Demo detaljplan 01", "demo_dp_02": "Demo detaljplan 02", "demo_dp_03": "Demo detaljplan 03"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CSS = ("body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; color: #1f2933; } "
       "h1 { font-size: 17pt; margin-top: 18pt; } h2 { font-size: 13pt; margin-top: 12pt; } "
       "h3 { font-size: 11pt; margin-top: 8pt; } p { margin: 4pt 0; } "
       "td { border: 1px solid #c4ccd4; padding: 4pt; vertical-align: top; } .liten { color: #52606d; font-size: 9pt; }")


def text_of(element) -> str:
    return "".join(t.text or "" for t in element.iter(W + "t")).strip()


def docx_to_html(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(W + "body")
    parts: list[str] = []
    started = False
    for child in body:
        if child.tag == W + "p":
            style = child.find(f"{W}pPr/{W}pStyle")
            level = re.fullmatch(r"Rubrik([1-3])", style.get(W + "val") if style is not None else "")
            text = text_of(child)
            if level:
                started = True
            if started and text:
                parts.append(f"<h{level.group(1)}>{html.escape(text)}</h{level.group(1)}>" if level
                             else f"<p>{html.escape(text)}</p>")
        elif child.tag == W + "tbl" and started:
            rows = []
            for row in child.iter(W + "tr"):
                cells = ["<td>" + "<br>".join(html.escape(text_of(p)) for p in cell.iter(W + "p") if text_of(p)) + "</td>"
                         for cell in row.iter(W + "tc")]
                rows.append("<tr>" + "".join(cells) + "</tr>")
            parts.append("<table width='100%' cellspacing='0'>" + "".join(rows) + "</table><p></p>")
    return "".join(parts)


def write_pdf(html_text: str, target: Path) -> None:
    document = QTextDocument()
    document.setHtml(f"<html><head><style>{CSS}</style></head><body>{html_text}</body></html>")
    writer = QPdfWriter(str(target))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(20, 18, 20, 18), QPageLayout.Unit.Millimeter)
    document.print(writer)


def main(docx: Path, out: Path) -> None:
    app = QGuiApplication([])  # texten ritas med Qt, som kräver en applikation även utan fönster
    body = docx_to_html(docx)
    for plan, name in PLANER.items():
        folder = out / plan
        folder.mkdir(parents=True, exist_ok=True)
        write_pdf(f"<h1 style='font-size:24pt'>Planbeskrivning</h1><p>{html.escape(name)}</p>"
                  "<p class='liten'>Testhandling för webbkartan. Texten är demoplanens.</p>" + body,
                  folder / "planbeskrivning.pdf")
        write_pdf(f"<h1 style='font-size:24pt'>Dagvattenutredning</h1><p>{html.escape(name)}</p>"
                  "<p class='liten'>Testhandling för webbkartan.</p>"
                  "<h2>Sammanfattning</h2><p>Dagvattnet från planområdet fördröjs i kvarteret innan det leds till det "
                  "kommunala nätet. Utredningen visar att ledningsnätet har tillräcklig kapacitet.</p>",
                  folder / "dagvattenutredning.pdf")
        print(f"{plan}: planbeskrivning.pdf, dagvattenutredning.pdf")
    del app


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
