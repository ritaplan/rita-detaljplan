"""Färgerna för användningsområden: den valda färgplattan, att katalogens färgnamn stämmer med BFS 2020:6, och att paletten
håller ihop så att ingen färg tar över kartan (kräver QGIS Python)."""
import itertools
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PlanCase  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsProject
    from qgis.PyQt.QtGui import QColor

    from rita_detaljplan.core.project import upgrade_symbology
    from rita_detaljplan.core.symbology import FARGER, has_current_colours

CATALOG = ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json"

# Färgnamn per användning i BFS 2020:6, avsnitt 4 till 6 (Boverkets allmänna råd om redovisning av reglering i detaljplan).
# Katalogen skriver GCVÄG där föreskriften skriver GC-VÄG.
BFS_2020_6 = {
    "TORG": "Ljusgrå", "VÄG": "Ljusgrå", "GATA": "Ljusgrå", "GCVÄG": "Ljusgrå", "P-PLATS": "Ljusgrå",
    "PARK": "Ljusgrön", "NATUR": "Ljusgrön", "SKYDD": "Ljusgrön",
    "B": "Gul", "C": "Brun", "D": "Röd", "E": "Blågrå", "F": "Grå", "G": "Grå", "H": "Brun", "J": "Blågrå", "K": "Brun",
    "L": "Grön", "M": "Lila", "N": "Grön", "O": "Orange", "P": "Grå", "R": "Orange", "S": "Röd", "T": "Grå", "U": "Röd",
    "V": "Grå", "Z": "Beige", "Y": "Rosa", "W": "Blå",
}

# Färgplattan ("lite mer färg"): bokens akvarellfärger utjämnade till ett gemensamt band av ljushet och mättnad.
PALETT = {
    "Gul": (250, 238, 145), "Brun": (197, 151, 96), "Beige": (215, 215, 158), "Orange": (244, 182, 124),
    "Röd": (240, 158, 134), "Rosa": (249, 180, 191), "Lila": (195, 173, 202), "Blå": (191, 230, 254),
    "Blågrå": (167, 199, 226), "Grön": (155, 205, 165), "Ljusgrön": (199, 237, 185), "Grå": (216, 215, 215),
    "Ljusgrå": (239, 238, 234),
}
BEIGE = (215, 215, 158)  # Z verksamheter: fastställd av användaren


def oklab(rgb):
    """sRGB (0-255) till OKLab (L, a, b)."""
    def linear(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def distance(a, b):
    """Färgavstånd i OKLab gånger 100 (2 knappt märkbart, 5 tydligt, 10 klart skilda)."""
    return 100 * math.dist(oklab(a), oklab(b))


def uses():
    """(beteckning, färgnamn, formulering) för varje användningsbestämmelse i katalogen (utom fritext)."""
    entries = json.loads(CATALOG.read_text(encoding="utf-8"))["entries"]
    return [((e["beteckning"] or "").rstrip("#"), e["farg"], e["formulering"]) for e in entries
            if e["typ"] == "Användningsbestämmelse" and e.get("farg") and not (e["beteckning"] or "").startswith("[")]


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ColourTests(unittest.TestCase):
    def test_the_catalogue_uses_the_colour_names_of_bfs_2020_6(self):
        wrong = [f"{letter} {text}: katalogen {name}, BFS 2020:6 {BFS_2020_6.get(letter)}"
                 for letter, name, text in uses() if BFS_2020_6.get(letter) != name]
        self.assertEqual(wrong, [])
        self.assertEqual({letter for letter, _name, _text in uses()}, set(BFS_2020_6), "samma användningar")

    def test_the_colour_names_have_the_chosen_palette(self):
        self.assertEqual(dict(FARGER), PALETT)

    def test_z_is_beige_o_and_r_are_orange_and_y_is_a_muted_rose(self):
        self.assertEqual(FARGER[BFS_2020_6["Z"]], BEIGE)
        red, green, blue = FARGER["Beige"]
        self.assertLessEqual(abs(red - green), 10, "beige är en dämpad gulbrun ton, inte orange")
        for letter in ("O", "R"):
            self.assertEqual(BFS_2020_6[letter], "Orange", letter)
        self.assertEqual(BFS_2020_6["Y"], "Rosa")

    def test_the_table_has_exactly_the_colour_names_of_the_catalogue(self):
        entries = json.loads(CATALOG.read_text(encoding="utf-8"))["entries"]
        self.assertEqual({e["farg"] for e in entries if e.get("farg")}, set(FARGER))

    def test_no_colour_takes_over_the_map(self):
        """Alla färger är ljusa och dämpade: ett smalt band av ljushet och en gräns för mättnaden (OKLCH)."""
        for name, rgb in FARGER.items():
            lightness, a, b = oklab(rgb)
            chroma = math.hypot(a, b)
            self.assertGreaterEqual(lightness, 0.70, f"{name} är för mörk")
            self.assertLessEqual(lightness, 0.96, name)
            self.assertLessEqual(chroma, 0.12, f"{name} är för intensiv")

    def test_the_colours_go_together_and_can_still_be_told_apart(self):
        """Inget par ligger närmare än 5 (tydligt skilda), och bandet av ljushet är smalt så att paletten hänger ihop."""
        closest = min((distance(a, b), x, y) for (x, a), (y, b) in itertools.combinations(FARGER.items(), 2))
        self.assertGreaterEqual(closest[0], 5, f"för lika: {closest[1]} och {closest[2]}")
        lightness = [oklab(rgb)[0] for rgb in FARGER.values()]
        self.assertLessEqual(max(lightness) - min(lightness), 0.26)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SavedProjectColourTests(PlanCase):
    def beige(self):
        use = self.layers["anvandning_yta"]
        category = next(c for c in use.renderer().categories() if c.value() == "Beige")
        colour = category.symbol().symbolLayer(0).color()
        return colour.red(), colour.green(), colour.blue()

    def test_a_project_saved_with_the_old_colours_is_restyled_with_the_new_when_opened(self):
        use = self.layers["anvandning_yta"]
        self.assertTrue(has_current_colours(use))
        self.assertEqual(self.beige(), FARGER["Beige"])
        renderer = use.renderer()
        categories = renderer.categories()
        index = next(i for i, c in enumerate(categories) if c.value() == "Beige")
        old = categories[index].symbol().clone()
        old.symbolLayer(0).setColor(QColor(255, 203, 131))  # Z verksamheter som den ritades förut (orange)
        renderer.updateCategorySymbol(index, old)
        self.assertEqual(self.beige(), (255, 203, 131))
        self.assertFalse(has_current_colours(use))
        self.assertTrue(upgrade_symbology(QgsProject.instance()), "ritas om")
        self.assertTrue(has_current_colours(use))
        self.assertEqual(self.beige(), BEIGE)


if __name__ == "__main__":
    unittest.main()
