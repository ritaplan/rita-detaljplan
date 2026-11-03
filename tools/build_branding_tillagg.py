"""Bygger bannrar och social preview för Rita Detaljplans två tillägg: webbkartan för Origo och pluginet för Hajk.

    python-qgis.bat tools/build_branding_tillagg.py <mapp med Archivo-var.ttf och IBMPlexMono-Regular.ttf> \
        <mapp till rita-detaljplan-origomap> <mapp till rita-detaljplan-hajk>

Samma märke (D), färger och typsnitt som i build_branding.py (som den här filen återanvänder), men med en egen slogan
och en egen etikett överst. Skriver docs/images/banner-ljus.svg, banner-mork.svg och social-preview.png i vardera repot.
Typsnittsfilerna följer inte med i repot. Körs med QGIS Python (behöver Qt, inte QGIS-kärnan).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_branding import (ACCENT, INK, PAPER, Face, mark, render_png, svg, text_path)  # noqa: E402,F401
from qgis.PyQt.QtGui import QFontDatabase, QGuiApplication  # noqa: E402

ADDONS = {
    "origomap": {
        "label": "WEBBKARTA · ORIGO",
        "slogan": "Detaljplaner i din Origo-karta",
        "url": "github.com/ritaplan/rita-detaljplan-origomap",
        "title": "Rita Detaljplan – detaljplaner i din Origo-karta",
    },
    "hajk": {
        "label": "PLUGIN · HAJK",
        "slogan": "Detaljplaner i din Hajk-karta",
        "url": "github.com/ritaplan/rita-detaljplan-hajk",
        "title": "Rita Detaljplan – detaljplaner i din Hajk-karta",
    },
}


def dark_banner(addon: dict, title: Face, mono_14: Face, mono_13: Face, mono_20: Face) -> str:
    """Som build_branding.dark_banner, med egen etikett, slogan och adress."""
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
    parts = [f'  <rect width="{w}" height="{h}" fill="{INK}"/>',
             f'  <g transform="translate({pad_x} {mark_y:.2f}) scale(1.2)">{mark("L", PAPER, INK)}</g>']
    base = pad_y + mono_14.ascent
    parts.append(text_path(mono_14.outline(addon["label"], pad_x, base, spacing=0.12 * 14), "#A9ADB2"))
    parts.append(text_path(mono_14.outline("GPL-2.0-OR-LATER", w - pad_x, base, spacing=0.12 * 14, align="right"), "#A9ADB2"))
    for n, word in enumerate(("Rita", "Detaljplan")):
        line_top = text_top + n * 92
        baseline = line_top + (92 - title.line) / 2 + title.ascent
        parts.append(text_path(title.outline(word, x_text, baseline, spacing=spacing), PAPER))
    slogan_base = text_top + 2 * 92 + 24 + mono_20.ascent
    parts.append(text_path(mono_20.outline(addon["slogan"], x_text, slogan_base), "#C9CCD0"))
    bottom_top = h - pad_y - bottom_h
    url_w = mono_13.width(addon["url"])
    parts.append(f'  <line x1="{pad_x}" y1="{bottom_top + bottom_h / 2:.2f}" x2="{w - pad_x - url_w - 20:.2f}" '
                 f'y2="{bottom_top + bottom_h / 2:.2f}" stroke="#3A3D42" stroke-width="1"/>')
    parts.append(text_path(mono_13.outline(addon["url"], w - pad_x, bottom_top + mono_13.ascent, align="right"), "#A9ADB2"))
    return svg(w, h, "\n".join(parts), addon["title"])


def light_banner(addon: dict, title: Face, mono_16: Face) -> str:
    """Som build_branding.light_banner, med egen slogan."""
    w, h = 1280, 640
    title_h = 64.0
    total = 220 + 36 + title_h + 14 + mono_16.line
    top = (h - total) / 2
    parts = [f'  <rect width="{w}" height="{h}" fill="{PAPER}"/>',
             f'  <g transform="translate({w / 2 - 110} {top:.2f}) scale(1.1)">{mark("L", INK, PAPER)}</g>']
    title_top = top + 220 + 36
    parts.append(text_path(title.outline("Rita Detaljplan", w / 2, title_top + (title_h - title.line) / 2 + title.ascent,
                                         spacing=-0.03 * 64, align="center"), INK))
    slogan_top = title_top + title_h + 14
    parts.append(text_path(mono_16.outline(addon["slogan"], w / 2, slogan_top + mono_16.ascent,
                                           spacing=0.04 * 16, align="center"), "#4A4D52"))
    return svg(w, h, "\n".join(parts), addon["title"])


def main(font_dir: Path, targets: dict[str, Path]) -> None:
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
        dark = dark_banner(addon, archivo_100, mono[14], mono[13], mono[20])
        light = light_banner(addon, archivo_64, mono[16])
        (images / "banner-mork.svg").write_text(dark, encoding="utf-8", newline="\n")
        (images / "banner-ljus.svg").write_text(light, encoding="utf-8", newline="\n")
        render_png(dark, images / "social-preview.png", 1280, 640)
        print("skrev bannrar och social preview i", images)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), {"origomap": Path(sys.argv[2]), "hajk": Path(sys.argv[3])})
