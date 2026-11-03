"""Bygger märken, bannrar och social preview för Rita Detaljplans två tillägg: webbkartan för Origo (DO) och pluginet
för Hajk (DH).

    python-qgis.bat tools/build_branding_tillagg.py <mapp med Archivo-var.ttf och IBMPlexMono-Regular.ttf> \
        <mapp till rita-detaljplan-origomap> <mapp till rita-detaljplan-hajk> [<mapp med webbplatsens bilder>]

Samma typsnitt, färger och bokstavsstil som i build_branding.py (som den här filen återanvänder för text och bild), men
med två bokstäver per märke: D för Detaljplan och O för Origo respektive H för Hajk, ritade som linjer med fyrkantiga
brytpunkter och ett rött streckat gummiband. Plattan har den ljusa gummibandsröda som webbplatsen använder för
"Tidig version" (#FDF1EE med kanten #F3C2B6), så att tilläggen inte förväxlas med själva QGIS-pluginen.

Skriver i vardera repot docs/images/: ikon.svg, banner-ljus.svg, banner-mork.svg och social-preview.png. Anges en mapp
för webbplatsens bilder skrivs även rita-detaljplan-origo.svg och rita-detaljplan-hajk.svg dit.
Typsnittsfilerna följer inte med i repot. Körs med QGIS Python (behöver Qt, inte QGIS-kärnan).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_branding import ACCENT, INK, PAPER, Face, render_png, svg, text_path  # noqa: E402
from qgis.PyQt.QtGui import QFontDatabase, QGuiApplication  # noqa: E402

TINT, TINT_LINE, MUTED = "#FDF1EE", "#F3C2B6", "#62666B"

ADDONS = {
    "origomap": {
        "letter": "O",
        "name": "Detaljplaner i Origo",
        "label": "WEBBKARTA · ORIGO",
        "slogan": "Detaljplaner i din Origo-karta",
        "url": "github.com/ritaplan/rita-detaljplan-origomap",
        "title": "Rita Detaljplan – detaljplaner i din Origo-karta",
        "web_icon": "rita-detaljplan-origo.svg",
    },
    "hajk": {
        "letter": "H",
        "name": "Detaljplaner i Hajk",
        "label": "PLUGIN · HAJK",
        "slogan": "Detaljplaner i din Hajk-karta",
        "url": "github.com/ritaplan/rita-detaljplan-hajk",
        "title": "Rita Detaljplan – detaljplaner i din Hajk-karta",
        "web_icon": "rita-detaljplan-hajk.svg",
    },
}

# -- bokstäverna --------------------------------------------------------------------------------------------------------
# Två bokstäver i en ruta på 200 x 200, var och en 64 bred och 116 hög, med 28 mellan. D är pluginets D, O är åttkanten
# från Ö-märket och H är två stolpar med gummibandet som tvärstreck.
_W, _H, _GAP, _X0, _Y0 = 64, 116, 28, 22, 42


def _points(points, ox, oy):
    return " ".join(f"{x + ox},{y + oy}" for x, y in points)


def _line(points, ox, oy, color):
    return (f'<polyline points="{_points(points, ox, oy)}" fill="none" stroke="{color}" stroke-width="10" '
            f'stroke-linejoin="miter"/>')


def _band(points, ox, oy, color):
    return (f'<polyline points="{_points(points, ox, oy)}" fill="none" stroke="{color}" stroke-width="6" '
            f'stroke-dasharray="11 8"/>')


def _squares(points, ox, oy, fill, stroke):
    rects = "".join(f'<rect x="{x + ox - 7}" y="{y + oy - 7}" width="14" height="14"/>' for x, y in points)
    return f'<g fill="{fill}" stroke="{stroke}" stroke-width="4.5">{rects}</g>'


def _letter_d(ox, oy, ink, band, fill):
    corners = [(0, 0), (38, 0), (64, 37), (64, 79)]
    cross = f'<path d="M{ox} {oy + 100}V{oy + 132}M{ox - 14} {oy + 116}H{ox + 14}" stroke="{band}" stroke-width="4"/>'
    return (_line([(0, 116)] + corners, ox, oy, ink) + _band([(18, 116), (38, 116), (64, 79)], ox, oy, band) + cross
            + _squares(corners, ox, oy, fill, ink))


def _letter_o(ox, oy, ink, band, fill):
    ring = [(0, 30), (18, 0), (46, 0), (64, 30), (64, 86), (46, 116), (18, 116)]
    return _line(ring, ox, oy, ink) + _band([(18, 116), (0, 86), (0, 30)], ox, oy, band) + _squares(ring, ox, oy, fill, ink)


def _letter_h(ox, oy, ink, band, fill):
    ends = [(0, 0), (0, 116), (64, 0), (64, 116)]
    return (_line([(0, 0), (0, 116)], ox, oy, ink) + _line([(64, 0), (64, 116)], ox, oy, ink)
            + _band([(0, 58), (64, 58)], ox, oy, band) + _squares(ends, ox, oy, fill, ink))


def letters(second: str, ink: str, band: str, fill: str) -> str:
    """D och därefter O eller H, i en ruta på 200 x 200 med bokstäverna centrerade."""
    second_letter = {"O": _letter_o, "H": _letter_h}[second]
    return (_letter_d(_X0, _Y0, ink, band, fill) + second_letter(_X0 + _W + _GAP, _Y0, ink, band, fill))


def tile_icon(addon: dict) -> str:
    """Märket på sin platta: ljus gummibandsröd med mörka bokstäver och rött gummiband."""
    body = (f'  <rect x="1" y="1" width="198" height="198" rx="28" fill="{TINT}" stroke="{TINT_LINE}" stroke-width="2"/>\n'
            f'  <g>{letters(addon["letter"], INK, ACCENT, TINT)}</g>')
    return svg(48, 48, body, addon["name"], "0 0 200 200")


# -- bannrar ------------------------------------------------------------------------------------------------------------
def two_line_banner(addon: dict, scheme: dict, title: Face, mono_14: Face, mono_13: Face, mono_20: Face) -> str:
    """Rubrik på två rader med märket till vänster, etikett överst och adress nederst (mörk banner och social preview)."""
    w, h, pad_y, pad_x = 1280, 640, 80, 88
    top_h, bottom_h = mono_14.line, mono_13.line
    text_h = 2 * 92 + 24 + mono_20.line
    mid_h = max(240.0, text_h)
    gap = (h - 2 * pad_y - top_h - mid_h - bottom_h) / 2
    mid_top = pad_y + top_h + gap
    mark_y = mid_top + (mid_h - 240) / 2
    text_top = mid_top + (mid_h - text_h) / 2
    spacing = -0.035 * 100
    x_text = pad_x + 240 + 64
    scale = 1.3
    parts = [f'  <rect width="{w}" height="{h}" fill="{scheme["bg"]}"/>',
             f'  <g transform="translate({pad_x + (240 - 200 * scale) / 2:.2f} {mark_y + (240 - 200 * scale) / 2:.2f}) '
             f'scale({scale})">{letters(addon["letter"], scheme["ink"], ACCENT, scheme["bg"])}</g>']
    base = pad_y + mono_14.ascent
    parts.append(text_path(mono_14.outline(addon["label"], pad_x, base, spacing=0.12 * 14), scheme["muted"]))
    parts.append(text_path(mono_14.outline("GPL-2.0-OR-LATER", w - pad_x, base, spacing=0.12 * 14, align="right"),
                           scheme["muted"]))
    for n, word in enumerate(("Rita", "Detaljplan")):
        line_top = text_top + n * 92
        baseline = line_top + (92 - title.line) / 2 + title.ascent
        parts.append(text_path(title.outline(word, x_text, baseline, spacing=spacing), scheme["title"]))
    slogan_base = text_top + 2 * 92 + 24 + mono_20.ascent
    parts.append(text_path(mono_20.outline(addon["slogan"], x_text, slogan_base), scheme["slogan"]))
    bottom_top = h - pad_y - bottom_h
    url_w = mono_13.width(addon["url"])
    parts.append(f'  <line x1="{pad_x}" y1="{bottom_top + bottom_h / 2:.2f}" x2="{w - pad_x - url_w - 20:.2f}" '
                 f'y2="{bottom_top + bottom_h / 2:.2f}" stroke="{scheme["rule"]}" stroke-width="1"/>')
    parts.append(text_path(mono_13.outline(addon["url"], w - pad_x, bottom_top + mono_13.ascent, align="right"),
                           scheme["muted"]))
    return svg(w, h, "\n".join(parts), addon["title"])


def centered_banner(addon: dict, title: Face, mono_16: Face) -> str:
    """Ljus banner med märket, rubriken och sloganen centrerade (för README i ljust läge)."""
    w, h = 1280, 640
    title_h = 64.0
    total = 220 + 36 + title_h + 14 + mono_16.line
    top = (h - total) / 2
    scale = 1.25
    parts = [f'  <rect width="{w}" height="{h}" fill="{TINT}"/>',
             f'  <g transform="translate({w / 2 - 100 * scale:.2f} {top + 110 - 100 * scale:.2f}) scale({scale})">'
             f'{letters(addon["letter"], INK, ACCENT, TINT)}</g>']
    title_top = top + 220 + 36
    parts.append(text_path(title.outline("Rita Detaljplan", w / 2, title_top + (title_h - title.line) / 2 + title.ascent,
                                         spacing=-0.03 * 64, align="center"), INK))
    slogan_top = title_top + title_h + 14
    parts.append(text_path(mono_16.outline(addon["slogan"], w / 2, slogan_top + mono_16.ascent,
                                           spacing=0.04 * 16, align="center"), "#4A4D52"))
    return svg(w, h, "\n".join(parts), addon["title"])


DARK = {"bg": INK, "ink": PAPER, "title": PAPER, "slogan": "#C9CCD0", "muted": "#A9ADB2", "rule": "#3A3D42"}
LIGHT = {"bg": TINT, "ink": INK, "title": INK, "slogan": "#4A4D52", "muted": MUTED, "rule": TINT_LINE}


def main(font_dir: Path, targets: dict[str, Path], web_images: Path | None = None) -> None:
    app = QGuiApplication([])  # noqa: F841 - Qt kräver en applikation för typsnitt
    for name in ("Archivo-var.ttf", "IBMPlexMono-Regular.ttf"):
        if QFontDatabase.addApplicationFont(str(font_dir / name)) < 0:
            raise SystemExit(f"Kunde inte läsa typsnittet {font_dir / name}")
    archivo_100, archivo_64 = Face("Archivo", 100, 500), Face("Archivo", 64, 500)
    mono = {size: Face("IBM Plex Mono", size, 400) for size in (13, 14, 16, 20)}
    for key, repo in targets.items():
        addon = ADDONS[key]
        images = repo / "docs" / "images"
        images.mkdir(parents=True, exist_ok=True)
        dark = two_line_banner(addon, DARK, archivo_100, mono[14], mono[13], mono[20])
        social = two_line_banner(addon, LIGHT, archivo_100, mono[14], mono[13], mono[20])
        (images / "banner-mork.svg").write_text(dark, encoding="utf-8", newline="\n")
        (images / "banner-ljus.svg").write_text(centered_banner(addon, archivo_64, mono[16]), encoding="utf-8",
                                                newline="\n")
        (images / "ikon.svg").write_text(tile_icon(addon), encoding="utf-8", newline="\n")
        render_png(social, images / "social-preview.png", 1280, 640)
        print("skrev märke, bannrar och social preview i", images)
        if web_images:
            (web_images / addon["web_icon"]).write_text(tile_icon(addon), encoding="utf-8", newline="\n")
            print("skrev", web_images / addon["web_icon"])


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), {"origomap": Path(sys.argv[2]), "hajk": Path(sys.argv[3])},
         Path(sys.argv[4]) if len(sys.argv) == 5 else None)
