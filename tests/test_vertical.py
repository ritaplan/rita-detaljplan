"""Höjd (3D) för bestämmelser: intervall, kropp och yta med höjdvärde i leveransen, import, stapling och uppgradering."""
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, filled, pick  # noqa: E402

if HAVE_QGIS:
    from rita_detaljplan.core import assignments, geopackage, model, rows, storage, validation, vertical
    from rita_detaljplan.core import import_ngp as im
    from test_export import ExportCase
    from schema_check import Checker

    CHECKER = Checker()
else:
    ExportCase = unittest.TestCase

SQUARE = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
HOLE = [[2.0, 2.0], [2.0, 8.0], [8.0, 8.0], [8.0, 2.0], [2.0, 2.0]]  # medurs: ett hål


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ExtentTests(unittest.TestCase):
    def test_no_height_is_flat_and_one_height_is_a_surface_with_a_limit_and_two_are_a_solid(self):
        self.assertEqual(vertical.Extent().kind, vertical.FLAT)
        self.assertEqual(vertical.Extent(upper=0).kind, vertical.HEIGHT)
        self.assertEqual(vertical.Extent(lower=-6, upper=0).kind, vertical.SOLID)

    def test_the_limit_follows_the_height_and_a_solid_has_none(self):
        self.assertEqual(vertical.Extent(upper=0).limit, "uppåt", "gäller inte ovanför höjden")
        self.assertEqual(vertical.Extent(lower=3).limit, "nedåt", "gäller inte under höjden")
        self.assertIsNone(vertical.Extent(lower=-6, upper=0).limit, "DP-0015, DP-0016")
        self.assertIsNone(vertical.Extent().limit)

    def test_the_surface_height_is_the_one_that_is_set(self):
        self.assertEqual(vertical.Extent(upper=4.5).height, 4.5)
        self.assertEqual(vertical.Extent(lower=-2).height, -2)
        self.assertIsNone(vertical.Extent(lower=-2, upper=3).height)

    def test_ranges_that_only_meet_do_not_overlap(self):
        garage, yard = vertical.Extent(-6, 0), vertical.Extent(lower=0)
        self.assertFalse(garage.overlaps(yard), "garaget går upp till 0 och gården börjar på 0")
        self.assertTrue(vertical.Extent(-6, 1).overlaps(yard))

    def test_an_unlimited_range_overlaps_everything(self):
        self.assertTrue(vertical.Extent().overlaps(vertical.Extent(-6, 0)))
        self.assertTrue(vertical.Extent().overlaps(vertical.Extent()))
        self.assertTrue(vertical.Extent(upper=0).overlaps(vertical.Extent(lower=-10)))
        self.assertFalse(vertical.Extent(upper=-10).overlaps(vertical.Extent(lower=0)))

    def test_an_area_with_several_provisions_covers_what_they_cover_together(self):
        hull = vertical.hull([vertical.Extent(0, 3), vertical.Extent(2, 8)])
        self.assertEqual((hull.lower, hull.upper), (0, 8))
        open_ended = vertical.hull([vertical.Extent(0, 3), vertical.Extent(lower=2)])
        self.assertEqual((open_ended.lower, open_ended.upper), (0, None), "en obegränsad bestämmelse gör ytan obegränsad")
        self.assertFalse(vertical.hull([]).limited, "en yta utan bestämmelser är obegränsad")

    def test_a_height_is_read_from_text_with_a_comma_and_rejects_nonsense(self):
        self.assertEqual(vertical.number("−6,5".replace("−", "-")), -6.5)
        self.assertIsNone(vertical.number(""))
        self.assertIsNone(vertical.number("abc"))
        self.assertIsNone(vertical.number(float("nan")))
        self.assertIsNone(vertical.number(None))
        self.assertIsNone(vertical.number(True))

    def test_the_two_heights_must_be_in_order(self):
        self.assertTrue(vertical.Extent(-6, 0).consistent)
        self.assertFalse(vertical.Extent(0, 0).consistent)
        self.assertFalse(vertical.Extent(3, 1).consistent)
        self.assertTrue(vertical.Extent(lower=3).consistent)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SolidTests(unittest.TestCase):
    def test_a_solid_has_a_bottom_a_top_and_a_wall_per_edge(self):
        faces = vertical.solid_faces([SQUARE], -6, 0)
        self.assertEqual(len(faces), 2 + 4)
        self.assertTrue(all(len(p) == 3 for face in faces for ring in face for p in ring), "alla koordinater har höjd")

    def test_the_top_faces_up_and_the_bottom_down(self):
        bottom, top = vertical.solid_faces([SQUARE], -6, 0)[:2]
        self.assertEqual({p[2] for p in top[0]}, {0})
        self.assertEqual({p[2] for p in bottom[0]}, {-6})
        self.assertGreater(vertical._area(top[0]), 0, "moturs sett uppifrån: normalen uppåt")
        self.assertLess(vertical._area(bottom[0]), 0, "medurs sett uppifrån: normalen nedåt")

    def test_every_face_is_closed(self):
        for face in vertical.solid_faces([SQUARE, HOLE], -1, 2):
            for ring in face:
                self.assertEqual(ring[0], ring[-1])

    def test_a_hole_adds_walls_and_a_ring_in_the_bottom_and_top(self):
        faces = vertical.solid_faces([SQUARE, HOLE], -1, 2)
        self.assertEqual(len(faces), 2 + 4 + 4)
        self.assertEqual(len(faces[0]), 2)
        self.assertEqual(len(faces[1]), 2)

    def test_walls_face_outwards(self):
        """Väggen längs södra kanten (y = 0) ska ha normalen mot söder (−y); moturs ring = ytan ligger till vänster."""
        wall = vertical.solid_faces([SQUARE], 0, 5)[2][0]
        a, b, c = wall[0], wall[1], wall[2]
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - b[i] for i in range(3)]
        normal_y = u[2] * v[0] - u[0] * v[2]
        self.assertLess(normal_y, 0)

    def test_reading_a_solid_gives_back_the_heights_and_the_outline(self):
        lower, upper, rings, prism = vertical.read_solid(vertical.solid_faces([SQUARE, HOLE], -6, 0))
        self.assertEqual((lower, upper), (-6, 0))
        self.assertTrue(prism)
        self.assertEqual(len(rings), 2, "ytterkonturen och hålet")
        self.assertEqual(sorted(map(tuple, rings[0]))[0], (0.0, 0.0))

    def test_a_sloped_solid_is_not_a_prism(self):
        slanted = [[[0, 0, 0], [10, 0, 0], [10, 10, 5], [0, 10, 5], [0, 0, 0]]]
        flat = [[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 0, 0]]]
        self.assertFalse(vertical.read_solid([flat, slanted])[3])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ExportTests(ExportCase):
    def use_row(self):
        return self.controller.rows_of("anvandning_yta", self.left.id())[0]

    def left_provision(self):
        identity = self.use_row()["objektidentitet"]
        return next(p for p in self.provisions() if p["objektidentitet"] == identity)

    def geometry(self, provision):
        return provision["bestammelsegeometri"][0]["geometri"]

    def test_a_provision_without_height_is_a_flat_surface_as_before(self):
        geometry = self.geometry(self.left_provision())
        self.assertEqual((geometry["typ"], geometry["dimension"]), ("yta", 2))
        self.assertNotIn("hojdsystem", geometry)

    def test_only_an_upper_height_gives_a_surface_with_a_height_value_and_the_limit_upwards(self):
        self.controller.set_bestammelse_height(self.use_row()["_fid"], None, 12.5)
        provision = self.left_provision()
        geometry = self.geometry(provision)
        self.assertEqual((geometry["typ"], geometry["dimension"], geometry["hojdsystem"]), ("yta", 3, "EPSG:5613"))
        self.assertEqual({p[2] for ring in geometry["position"]["coordinates"] for p in ring}, {12.5})
        self.assertEqual(provision["vertikalAvgransning"], "uppåt")

    def test_only_a_lower_height_gives_the_limit_downwards(self):
        self.controller.set_bestammelse_height(self.use_row()["_fid"], -3.0, None)
        provision = self.left_provision()
        self.assertEqual(provision["vertikalAvgransning"], "nedåt")
        self.assertEqual({p[2] for ring in self.geometry(provision)["position"]["coordinates"] for p in ring}, {-3.0})

    def test_two_heights_give_a_solid_without_a_vertical_limit(self):
        self.controller.set_bestammelse_height(self.use_row()["_fid"], -6.0, 0.0)
        provision = self.left_provision()
        geometry = self.geometry(provision)
        self.assertEqual((geometry["typ"], geometry["dimension"], geometry["hojdsystem"]), ("kropp", 3, "EPSG:5613"))
        self.assertEqual(geometry["position"]["type"], "MultiPolygon")
        self.assertEqual(len(geometry["position"]["coordinates"]), 6)
        self.assertNotIn("vertikalAvgransning", provision, "DP-0015 och DP-0016: en kropp får ingen avgränsning")

    def test_a_stored_limit_is_not_delivered_for_a_solid(self):
        row = self.use_row()
        self.controller.set_bestammelse_height(row["_fid"], -6.0, 0.0)
        from rita_detaljplan.core.project import apply_attributes
        apply_attributes(assignments.rows_layer(self.controller.project), [row["_fid"]], {"vertikalAvgransning": "uppåt"})
        self.assertNotIn("vertikalAvgransning", self.left_provision())

    def test_a_multipart_area_becomes_one_solid_per_part(self):
        wkt = "MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)), ((20 0, 30 0, 30 10, 20 10, 20 0)))"
        from qgis.core import QgsGeometry
        from rita_detaljplan.core import export_ngp as ex
        described = ex.geometry_descriptions(QgsGeometry.fromWkt(wkt), {}, 3006, vertical.Extent(-1, 2))
        self.assertEqual([d["geometri"]["typ"] for d in described], ["kropp", "kropp"], "ingen multikropp (DP-0004)")

    def test_a_line_never_gets_a_height(self):
        row = self.controller.rows_of("egenskap_linje", self.line.id())[0]
        with self.assertRaises(assignments.AssignmentError):
            self.controller.set_bestammelse_height(row["_fid"], None, 5.0)

    def test_the_delivery_still_follows_the_json_schema_with_a_solid_and_a_surface(self):
        self.controller.set_bestammelse_height(self.use_row()["_fid"], -6.0, 0.0)
        right = self.controller.rows_of("anvandning_yta", self.right.id())[0]
        self.controller.set_bestammelse_height(right["_fid"], None, 20.0)
        self.assertEqual(CHECKER.problems(self.export()), [])

    def test_a_property_only_regulates_the_uses_at_its_own_height(self):
        """Egenskapen på ytan INSIDE ligger över användningen till vänster: bara den som gäller på dess höjd regleras."""
        left = self.use_row()
        self.controller.set_bestammelse_height(left["_fid"], -6.0, 0.0)  # användningen till vänster ligger under marken
        prop_row = self.controller.rows_of("egenskap_yta", self.prop.id())[0]
        self.controller.set_bestammelse_height(prop_row["_fid"], 0.0, 9.0)  # egenskapen gäller 0 till 9 m
        prop = next(p for p in self.provisions() if p["objektidentitet"] == prop_row["objektidentitet"])
        self.assertNotIn(left["objektidentitet"], prop.get("reglerarAnvandningsbestammelse", []))

    def test_the_height_is_shown_in_the_description_of_a_row(self):
        self.controller.set_bestammelse_height(self.use_row()["_fid"], -6.0, 0.0)
        self.assertIn("−6,0 till 0,0 m", rows.describe(self.use_row()))
        self.assertNotIn(" m)", rows.describe(self.controller.rows_of("anvandning_yta", self.right.id())[0]))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SettingTests(ExportCase):
    def row(self):
        return self.controller.rows_of("anvandning_yta", self.left.id())[0]

    def test_the_lower_height_must_be_below_the_upper(self):
        with self.assertRaises(assignments.AssignmentError):
            self.controller.set_bestammelse_height(self.row()["_fid"], 5.0, 5.0)

    def test_the_heights_are_read_back(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], -2.5, 7.0)
        self.assertEqual(self.controller.bestammelse_height(self.row()["_fid"]),
                         {"hojdUnderkant": -2.5, "hojdOverkant": 7.0})

    def test_clearing_the_heights_makes_the_provision_flat_again(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], -2.5, 7.0)
        self.controller.set_bestammelse_height(self.row()["_fid"], None, None)
        self.assertFalse(vertical.extent_of(self.row()).limited)

    def test_setting_one_height_stores_the_limit_it_means_and_two_clear_it(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], None, 4.0)
        self.assertEqual(self.row()["vertikalAvgransning"], "uppåt")
        self.controller.set_bestammelse_height(self.row()["_fid"], 1.0, 4.0)
        self.assertIsNone(self.row()["vertikalAvgransning"])

    def test_the_heights_follow_when_an_area_is_split_and_its_rows_are_copied(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], -2.5, 7.0)
        identity = self.row()["yta"]
        assignments.copy_rows(self.controller.project, "anvandning_yta", identity, "kopia")
        copied = assignments.read_rows(self.controller.project, "anvandning_yta", "kopia")
        self.assertEqual([(r["hojdUnderkant"], r["hojdOverkant"]) for r in copied], [(-2.5, 7.0)])

    def test_changing_the_provision_keeps_its_height(self):
        row = self.row()
        self.controller.set_bestammelse_height(row["_fid"], -2.5, 7.0)
        entry = self.catalog.get(row["planbestammelsekatalogreferens"])
        self.controller.update_bestammelse(row["_fid"], entry, filled(entry), None, None, None)
        self.assertEqual(self.controller.bestammelse_height(row["_fid"]), {"hojdUnderkant": -2.5, "hojdOverkant": 7.0})


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class HeightDialogTests(ExportCase):
    """Rutan Höjd… byggs och används på riktigt (inga låtsasfunktioner): Qt 6-fel syns bara då."""

    def row(self):
        return self.controller.rows_of("anvandning_yta", self.left.id())[0]

    def dialog(self):
        from rita_detaljplan.gui.height_dialog import HeightDialog
        dialog = HeightDialog(self.row()["_fid"], self.controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_a_provision_without_height_opens_with_both_fields_off(self):
        dialog = self.dialog()
        self.assertFalse(dialog.use_lower.isChecked() or dialog.use_upper.isChecked())
        self.assertFalse(dialog.lower.isEnabled() or dialog.upper.isEnabled())
        self.assertEqual(dialog.summary.text(), "Gäller på alla höjder.")

    def test_the_dialog_shows_the_saved_heights(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], -6.0, 0.0)
        dialog = self.dialog()
        self.assertTrue(dialog.use_lower.isChecked() and dialog.use_upper.isChecked())
        self.assertEqual((dialog.lower.value(), dialog.upper.value()), (-6.0, 0.0))
        self.assertIn("kropp", dialog.summary.text())

    def test_one_height_says_which_limit_it_gives(self):
        dialog = self.dialog()
        dialog.use_upper.setChecked(True)
        dialog.upper.setValue(12.0)
        self.assertEqual(dialog.extent().limit, "uppåt")
        self.assertIn("uppåt", dialog.summary.text())
        self.assertTrue(dialog.upper.isEnabled())

    def test_wrong_order_blocks_saving(self):
        from qgis.PyQt.QtWidgets import QDialogButtonBox
        dialog = self.dialog()
        dialog.use_lower.setChecked(True)
        dialog.use_upper.setChecked(True)
        dialog.lower.setValue(5.0)
        dialog.upper.setValue(1.0)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
        self.assertIn("Underkanten", dialog.error.text())

    def test_accepting_saves_the_heights_and_unchecking_clears_them(self):
        dialog = self.dialog()
        dialog.use_lower.setChecked(True)
        dialog.lower.setValue(-3.0)
        dialog.accept()
        self.assertEqual(self.controller.bestammelse_height(self.row()["_fid"]),
                         {"hojdUnderkant": -3.0, "hojdOverkant": None})
        again = self.dialog()
        again.use_lower.setChecked(False)
        again.accept()
        self.assertFalse(vertical.extent_of(self.row()).limited)

    def test_the_assign_dialog_has_a_height_button_that_follows_the_selected_row(self):
        from qgis.core import QgsPointXY
        from rita_detaljplan.gui.assign_dialog import AssignDialog
        candidates = [c for c in self.controller.candidates_at(QgsPointXY(20, 20), 0.5) if c.table == "anvandning_yta"]
        dialog = AssignDialog(self.controller, lambda: self.catalog, candidates)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.btn_height.text(), "Höjd…")
        dialog.rows_list.setCurrentRow(0)
        self.assertTrue(dialog.btn_height.isEnabled(), "en användningsbestämmelse är markerad")
        self.assertEqual(dialog._selected_row()["tabell"], "anvandning_yta")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ValidationTests(ExportCase):
    def row(self):
        return self.controller.rows_of("anvandning_yta", self.left.id())[0]

    def issues(self, code=None):
        found = self.controller.validate(self.catalog)
        return [i for i in found if code is None or i.code == code]

    def test_a_height_that_is_consistent_gives_no_issue(self):
        self.controller.set_bestammelse_height(self.row()["_fid"], -6.0, 0.0)
        self.assertEqual([i for i in self.issues() if "höjd" in i.text.lower() or "kant" in i.text.lower()], [])

    def test_a_wrong_order_in_the_data_is_an_error(self):
        from rita_detaljplan.core.project import apply_attributes
        apply_attributes(assignments.rows_layer(self.controller.project), [self.row()["_fid"]],
                         {"hojdUnderkant": 5.0, "hojdOverkant": 1.0})
        errors = [i for i in self.issues() if "Underkanten" in i.text]
        self.assertEqual([i.severity for i in errors], [validation.ERROR])

    def test_a_stored_limit_on_a_solid_is_a_warning_that_says_it_is_left_out(self):
        from rita_detaljplan.core.project import apply_attributes
        self.controller.set_bestammelse_height(self.row()["_fid"], -6.0, 0.0)
        apply_attributes(assignments.rows_layer(self.controller.project), [self.row()["_fid"]],
                         {"vertikalAvgransning": "nedåt"})
        found = self.issues("DP-0015")
        self.assertTrue(any("kropp" in i.text and i.severity == validation.WARNING for i in found), found)

    def test_a_limit_that_contradicts_the_height_is_a_warning(self):
        from rita_detaljplan.core.project import apply_attributes
        self.controller.set_bestammelse_height(self.row()["_fid"], None, 4.0)
        apply_attributes(assignments.rows_layer(self.controller.project), [self.row()["_fid"]],
                         {"vertikalAvgransning": "nedåt"})
        self.assertTrue(any("stämmer inte med höjden" in i.text for i in self.issues()))

    def test_a_height_on_a_line_is_a_warning(self):
        from rita_detaljplan.core.project import apply_attributes
        line = self.controller.rows_of("egenskap_linje", self.line.id())[0]
        apply_attributes(assignments.rows_layer(self.controller.project), [line["_fid"]], {"hojdOverkant": 3.0})
        self.assertTrue(any("bara anges för ytor" in i.text and i.severity == validation.WARNING for i in self.issues()))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class StackingTests(ExportCase):
    """Användningar på olika höjd får ligga över varandra i planet (garaget under gården)."""

    def left_row(self):
        return self.controller.rows_of("anvandning_yta", self.left.id())[0]

    def overlaps(self):
        return [i for i in self.controller.validate(self.catalog) if i.code == "DP-Krav-0013"]

    def test_a_new_area_drawn_over_an_unlimited_use_is_cut_away_as_before(self):
        self.assertIsNone(self.draw("anvandning_yta", INSIDE), "helt inom en användning som gäller på alla höjder")

    def test_a_new_area_drawn_over_a_use_that_is_limited_in_height_is_kept_whole(self):
        self.controller.set_bestammelse_height(self.left_row()["_fid"], 0.0, None)  # användningen börjar vid marken
        garage = self.draw("anvandning_yta", INSIDE)
        self.assertIsNotNone(garage)
        self.assertAlmostEqual(garage.geometry().area(), 900.0, places=1, msg="inte beskuren")

    def test_stacked_uses_with_heights_that_do_not_overlap_give_no_overlap_error(self):
        self.controller.set_bestammelse_height(self.left_row()["_fid"], 0.0, None)
        garage = self.draw("anvandning_yta", INSIDE)
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", garage.id(), entry, filled(entry))
        row = self.controller.rows_of("anvandning_yta", garage.id())[0]
        self.assertTrue(self.overlaps(), "utan höjd gäller garaget på alla höjder och överlappar")
        self.controller.set_bestammelse_height(row["_fid"], -6.0, 0.0)
        self.assertEqual(self.overlaps(), [])

    def test_stacked_uses_whose_heights_overlap_still_give_the_overlap_error(self):
        self.controller.set_bestammelse_height(self.left_row()["_fid"], 0.0, None)
        garage = self.draw("anvandning_yta", INSIDE)
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", garage.id(), entry, filled(entry))
        row = self.controller.rows_of("anvandning_yta", garage.id())[0]
        self.controller.set_bestammelse_height(row["_fid"], -6.0, 2.0)  # sticker upp två meter över marken
        self.assertTrue(self.overlaps())

    def test_a_use_that_gets_a_height_later_is_cut_only_against_uses_at_the_same_height(self):
        self.controller.set_bestammelse_height(self.left_row()["_fid"], 0.0, None)
        garage = self.draw("anvandning_yta", INSIDE)
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", garage.id(), entry, filled(entry))
        row = self.controller.rows_of("anvandning_yta", garage.id())[0]
        self.controller.set_bestammelse_height(row["_fid"], -6.0, 0.0)
        layer = self.controller.layer("anvandning_yta")
        layer.changeGeometry(garage.id(), __import__("qgis.core", fromlist=["QgsGeometry"]).QgsGeometry.fromWkt(
            "MultiPolygon(((10 10, 45 10, 45 45, 10 45, 10 10)))"))
        from plan_case import pump
        pump()
        self.assertAlmostEqual(layer.getFeature(garage.id()).geometry().area(), 35 * 35, places=1,
                               msg="flyttas på sin egen höjd: inget klipps mot användningen ovanför")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ImportTests(unittest.TestCase):
    def solid(self, coords=None, lower=-6.0, upper=0.0):
        faces = vertical.solid_faces([coords or SQUARE], lower, upper)
        return {"geometri": {"typ": "kropp", "position": {"type": "MultiPolygon", "coordinates": faces},
                             "dimension": 3, "hojdsystem": "EPSG:5613"}}

    def surface(self, height):
        ring = [[x, y, height] for x, y in SQUARE]
        return {"geometri": {"typ": "yta", "position": {"type": "Polygon", "coordinates": [ring]}, "dimension": 3,
                             "hojdsystem": "EPSG:5613"}}

    def test_a_solid_is_read_as_its_outline_and_its_two_heights(self):
        geometry, extent, notes = im.build_area([self.solid()])
        self.assertAlmostEqual(geometry.area(), 100.0, places=3)
        self.assertEqual((extent.lower, extent.upper, notes), (-6.0, 0.0, []))

    def test_a_surface_with_a_height_and_the_limit_up_is_an_upper_height(self):
        geometry, extent, notes = im.build_area([self.surface(4.0)], "uppåt")
        self.assertEqual((extent.lower, extent.upper), (None, 4.0))
        self.assertAlmostEqual(geometry.area(), 100.0, places=3)

    def test_a_surface_with_a_height_and_the_limit_down_is_a_lower_height(self):
        _, extent, _ = im.build_area([self.surface(4.0)], "nedåt")
        self.assertEqual((extent.lower, extent.upper), (4.0, None))

    def test_a_height_without_a_limit_is_ignored_with_a_note(self):
        _, extent, notes = im.build_area([self.surface(4.0)], None)
        self.assertFalse(extent.limited)
        self.assertTrue(any("vertikal avgränsning" in n for n in notes))

    def test_three_coordinates_no_longer_crash_the_flat_reading(self):
        geometry = im.build_geometry([self.surface(4.0)])
        self.assertAlmostEqual(geometry.area(), 100.0, places=3)

    def test_the_plan_geometry_may_be_a_solid(self):
        self.assertAlmostEqual(im.build_geometry([self.solid()]).area(), 100.0, places=3)

    def test_a_limit_without_a_height_is_kept_on_the_provision(self):
        provision = im._provision({"vertikalAvgransning": "uppåt"}, vertical.Extent())
        self.assertEqual(provision.vertikal_avgransning, "uppåt")
        self.assertIsNone(im._provision({"vertikalAvgransning": "uppåt"}, vertical.Extent(upper=1)).vertikal_avgransning)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class RoundTripTests(ExportCase):
    def test_a_solid_survives_export_and_import_into_a_new_plan(self):
        from plan_case import PlanCase  # noqa: F401
        row = self.controller.rows_of("anvandning_yta", self.left.id())[0]
        self.controller.set_bestammelse_height(row["_fid"], -6.0, 0.0)
        parsed = im.parse(self.export())
        stacked = [p for a in parsed.areas for p in a.provisions if p.extent.kind == vertical.SOLID]
        self.assertEqual(len(stacked), 1)
        self.assertEqual((stacked[0].extent.lower, stacked[0].extent.upper), (-6.0, 0.0))
        footprints = sorted(round(a.geometry.area()) for a in parsed.areas if a.table == "anvandning_yta")
        self.assertEqual(footprints, [5000, 5000], "ytan i planet är oförändrad")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class UpgradeTests(unittest.TestCase):
    def test_the_schema_has_the_two_height_columns_in_the_provision_table(self):
        names = [field.name for field in model.BESTAMMELSE.fields]
        self.assertIn("hojdUnderkant", names)
        self.assertIn("hojdOverkant", names)
        self.assertGreaterEqual(model.SCHEMA_VERSION, 11)

    def test_an_older_geopackage_gets_the_columns(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            gpkg = geopackage.create_geopackage(Path(folder) / "gammal.gpkg", 3006)
            con = sqlite3.connect(str(gpkg))
            con.execute("ALTER TABLE bestammelse DROP COLUMN hojdUnderkant")
            con.execute("ALTER TABLE bestammelse DROP COLUMN hojdOverkant")
            con.execute("UPDATE dp_meta SET value='10' WHERE key='schema_version'")
            con.commit()
            con.close()
            self.assertTrue(geopackage.upgrade(gpkg))
            con = sqlite3.connect(str(gpkg))
            columns = [row[1] for row in con.execute("PRAGMA table_info(bestammelse)")]
            con.close()
            self.assertIn("hojdUnderkant", columns)
            self.assertIn("hojdOverkant", columns)
            self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_a_postgis_schema_from_version_10_gets_the_columns_and_nothing_else(self):
        sql = "\n".join(storage.postgis_upgrade("dp", 10, 3006))
        self.assertIn('ADD COLUMN IF NOT EXISTS "hojdUnderkant"', sql)
        self.assertIn('ADD COLUMN IF NOT EXISTS "hojdOverkant"', sql)
        self.assertNotIn("CREATE TABLE", sql)

    def test_an_older_postgis_schema_also_gets_them(self):
        self.assertIn("hojdOverkant", "\n".join(storage.postgis_upgrade("dp", 5, 3006)))

    def test_a_new_postgis_schema_has_them_from_the_start(self):
        self.assertIn("hojdOverkant", "\n".join(storage.ensure_schema("dp", 3006)))


if __name__ == "__main__":
    unittest.main()
