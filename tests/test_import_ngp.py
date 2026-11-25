"""Tolkningen av en leverans (import_ngp.parse), och att den kan skrivas till en ny plan (kräver QGIS för geometrin)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PlanCase, pick, pump  # noqa: E402

if HAVE_QGIS:
    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core import import_ngp as im


def polygon(coords):
    return {"geometri": {"typ": "yta", "position": {"type": "Polygon", "coordinates": [coords]}}}


def linestring(coords):
    return {"geometri": {"typ": "linje", "position": {"type": "LineString", "coordinates": coords}}}


SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
OTHER_SQUARE = [[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]
LINE = [[0, 0], [10, 0]]

PLAN_FEATURE = {"type": "Feature", "geometry": None, "properties": {
    "feature:typ": "detaljplan", "objektidentitet": "plan-1", "kommun": "Eskilstuna", "namn": "Kv Väktaren",
    "syfte": "Bostäder", "status": "samråd", "typ": "detaljplan", "beteckning": "DP 2026:1",
    "plangeometri": [polygon(SQUARE)],
}}


def use_feature(coords=SQUARE, ref="DP_KM_J2", **extra):
    return {"type": "Feature", "geometry": None, "properties": {
        "feature:typ": "användningsbestämmelse", "objektidentitet": f"row-{id(coords)}",
        "planbestammelsekatalogreferens": ref, "bestammelseformulering": "Bostäder", "bestammelsegeometri": [polygon(coords)],
        **extra,
    }}


def collection(*features):
    return {"type": "FeatureCollection", "feature:mediatyp": "x", "features": [PLAN_FEATURE, *features]}


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ParseTests(unittest.TestCase):
    def test_a_collection_without_a_plan_feature_is_rejected(self):
        with self.assertRaises(im.ImportError_):
            im.parse({"type": "FeatureCollection", "features": []})

    def test_something_that_is_not_a_feature_collection_is_rejected(self):
        with self.assertRaises(im.ImportError_):
            im.parse({"type": "Feature"})

    def test_a_plan_without_geometry_is_rejected(self):
        broken = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": None, "properties": {"feature:typ": "detaljplan"}}]}
        with self.assertRaises(im.ImportError_):
            im.parse(broken)

    def test_the_plan_attributes_are_read(self):
        plan = im.parse(collection())
        self.assertEqual((plan.attrs["kommun"], plan.attrs["namn"], plan.attrs["status"]),
                         ("Eskilstuna", "Kv Väktaren", "samråd"))
        self.assertAlmostEqual(plan.geometry.area(), 100.0)

    def test_two_provisions_on_the_same_geometry_become_one_area(self):
        plan = im.parse(collection(use_feature(), use_feature(ref="DP_KM_B1")))
        self.assertEqual(len(plan.areas), 1)
        self.assertEqual(plan.areas[0].table, "anvandning_yta")
        self.assertEqual([p.catalog_id for p in plan.areas[0].provisions], ["DP_KM_J2", "DP_KM_B1"])

    def test_provisions_on_different_geometries_become_different_areas(self):
        plan = im.parse(collection(use_feature(SQUARE), use_feature(OTHER_SQUARE)))
        self.assertEqual(len(plan.areas), 2)
        self.assertAlmostEqual(sum(a.geometry.area() for a in plan.areas), 200.0)

    def test_a_property_area_is_told_apart_from_a_property_line(self):
        area_feature = {"type": "Feature", "geometry": None, "properties": {
            "feature:typ": "egenskapsbestämmelse", "planbestammelsekatalogreferens": "DP_KM_E1",
            "bestammelseformulering": "e1", "bestammelsegeometri": [polygon(SQUARE)]}}
        line_feature = {"type": "Feature", "geometry": None, "properties": {
            "feature:typ": "egenskapsbestämmelse", "planbestammelsekatalogreferens": "DP_KM_UTFART",
            "bestammelseformulering": "Utfart", "bestammelsegeometri": [linestring(LINE)]}}
        plan = im.parse(collection(area_feature, line_feature))
        self.assertEqual({a.table for a in plan.areas}, {"egenskap_yta", "egenskap_linje"})

    def test_a_secondary_property_boundary_is_detected(self):
        feature = use_feature(ref="DP_KM_E1")
        feature["properties"]["feature:typ"] = "egenskapsbestämmelse"
        feature["properties"]["sekundarEgenskapsgrans"] = True
        plan = im.parse(collection(feature))
        self.assertTrue(plan.areas[0].sekundar)

    def test_values_motive_and_optional_fields_are_carried_over(self):
        feature = use_feature()
        feature["properties"].update({
            "bestammelsevarde": [{"beskrivning": "hojd", "variabelvarde": "10", "vardetyp": "max", "enhet": "meter"}],
            "planbestammelsebeskrivning": {"motiv": "Bostäder behövs i området"},
            "giltighetstid": 24, "borjarGallaEfter": 6,
        })
        plan = im.parse(collection(feature))
        provision = plan.areas[0].provisions[0]
        self.assertEqual(provision.motiv, "Bostäder behövs i området")
        self.assertEqual(provision.values, [{"beskrivning": "hojd", "variabelvarde": "10", "vardetyp": "max",
                                            "enhet": "meter"}])
        self.assertEqual((provision.giltighetstid, provision.borjar_galla_efter), (24, 6))

    def test_a_feature_without_valid_geometry_is_skipped_with_a_warning(self):
        broken = use_feature()
        broken["properties"]["bestammelsegeometri"] = []
        plan = im.parse(collection(broken))
        self.assertEqual(plan.areas, [])
        self.assertTrue(any("hoppades över" in w for w in plan.warnings))

    def multi(self, kind, geometry_type, coordinates):
        return {"geometri": {"typ": kind, "position": {"type": geometry_type, "coordinates": coordinates}}}

    def property_feature(self, geometry, ref="DP_KM_E1", values=(), oid="aaaaaaaa-1", text="Största byggnadsarea"):
        return {"type": "Feature", "geometry": None, "properties": {
            "feature:typ": "egenskapsbestämmelse", "objektidentitet": oid, "planbestammelsekatalogreferens": ref,
            "bestammelseformulering": text, "bestammelsegeometri": [geometry], "bestammelsevarde": list(values)}}

    @staticmethod
    def number(value, name="area"):
        return {"datatyp": "decimaltal", "beskrivning": name, "variabelvarde": value, "vardetyp": "max", "enhet": "procent"}

    @staticmethod
    def word(value, name="typ"):
        return {"datatyp": "text", "beskrivning": name, "variabelvarde": value}

    def test_a_use_in_two_parts_is_read_as_one_area_in_two_parts(self):
        use = use_feature()
        use["properties"]["bestammelsegeometri"] = [self.multi("multiyta", "MultiPolygon", [[SQUARE], [OTHER_SQUARE]])]
        plan = im.parse(collection(use))
        self.assertEqual(plan.warnings, [])
        (area,) = plan.areas
        self.assertEqual((area.table, len(area.geometry.asMultiPolygon())), ("anvandning_yta", 2))
        self.assertAlmostEqual(area.geometry.area(), 200.0)

    def test_a_hole_in_a_part_of_a_multi_area_is_kept(self):
        hole = [[2, 2], [2, 4], [4, 4], [4, 2], [2, 2]]
        use = use_feature()
        use["properties"]["bestammelsegeometri"] = [self.multi("multiyta", "MultiPolygon", [[SQUARE, hole], [OTHER_SQUARE]])]
        self.assertAlmostEqual(im.parse(collection(use)).areas[0].geometry.area(), 196.0)

    def test_multi_properties_go_to_the_layer_of_their_kind(self):
        area = self.property_feature(self.multi("multiyta", "MultiPolygon", [[SQUARE], [OTHER_SQUARE]]))
        line = self.property_feature(self.multi("multilinje", "MultiLineString", [LINE, [[0, 5], [10, 5]]]), ref="L", oid="b")
        point = self.property_feature(self.multi("multipunkt", "MultiPoint", [[1, 1], [2, 2]]), ref="P", oid="c")
        plan = im.parse(collection(area, line, point))
        self.assertEqual(plan.warnings, [])
        self.assertEqual(sorted(a.table for a in plan.areas), ["egenskap_linje", "egenskap_punkt", "egenskap_yta"])
        by_table = {a.table: a.geometry for a in plan.areas}
        self.assertEqual(len(by_table["egenskap_linje"].asMultiPolyline()), 2)
        self.assertEqual(len(by_table["egenskap_punkt"].asMultiPoint()), 2)

    def test_the_height_of_a_multi_area_is_read_like_that_of_a_single_one(self):
        raised = [[[[x, y, 12.5] for x, y in SQUARE]], [[[x, y, 12.5] for x, y in OTHER_SQUARE]]]
        feature = self.property_feature(self.multi("multiyta", "MultiPolygon", raised))
        from rita_detaljplan.core import vertical
        feature["properties"]["vertikalAvgransning"] = vertical.UPWARD
        extent = im.parse(collection(feature)).areas[0].provisions[0].extent
        self.assertEqual((extent.lower, extent.upper), (None, 12.5))

    def test_a_skipped_provision_is_named_in_the_warning(self):
        broken = self.property_feature(self.multi("kurva", "Curve", []), oid="1234abcd-9999", text="Markreservat")
        (warning,) = im.parse(collection(broken)).warnings
        for part in ("Markreservat", "1234abcd", "kurva", "hoppades över"):
            self.assertIn(part, warning)

    def test_different_values_on_the_same_ground_are_warned_about_once(self):
        whole = self.property_feature(polygon(SQUARE), values=[self.number("25.0")], oid="1eddc2a4", text="Area 25 %")
        part = self.property_feature(polygon([[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]]), values=[self.number("30.0")],
                                     oid="178da349", text="Area 30 %")
        other = self.property_feature(polygon([[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]]), values=[self.number("30.0")],
                                      oid="cea39e7b", text="Area 30 %")
        warnings = im.parse(collection(whole, part, other)).warnings
        self.assertEqual(len(warnings), 1, warnings)
        for text in ("Olika värden", "100 m²", "Area 25 %", "1eddc2a4", "Area 30 %", "178da349"):
            self.assertIn(text, warnings[0])

    def test_neighbours_the_same_value_and_different_subjects_are_not_warned_about(self):
        left, right = polygon(SQUARE), polygon([[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]])
        neighbours = [self.property_feature(left, values=[self.number("25")], oid="a"),
                      self.property_feature(right, values=[self.number("30")], oid="b")]
        self.assertEqual(im.parse(collection(*neighbours)).warnings, [], "delar bara en gräns")
        same = [self.property_feature(left, values=[self.number("30")], oid="a"),
                self.property_feature(left, values=[self.number("30.0")], oid="b")]
        self.assertEqual(im.parse(collection(*same)).warnings, [], "samma värde")
        subjects = [self.property_feature(left, values=[self.word("huvudbyggnad"), self.number("8")], oid="a"),
                    self.property_feature(left, values=[self.word("komplementbyggnad"), self.number("5")], oid="b")]
        self.assertEqual(im.parse(collection(*subjects)).warnings, [], "olika saker regleras")
        kinds = [self.property_feature(left, ref="E", values=[self.number("30")], oid="a"),
                 self.property_feature(left, ref="H", values=[self.number("8")], oid="b")]
        self.assertEqual(im.parse(collection(*kinds)).warnings, [], "olika bestämmelser")

    def test_heights_that_do_not_meet_are_not_in_conflict(self):
        low = [[[x, y, 3.0] for x, y in SQUARE]]
        high = [[[x, y, 6.0] for x, y in SQUARE]]
        from rita_detaljplan.core import vertical
        below = self.property_feature({"geometri": {"typ": "yta", "position": {"type": "Polygon", "coordinates": low}}},
                                      values=[self.number("25")], oid="a")
        below["properties"]["vertikalAvgransning"] = vertical.UPWARD  # upp till 3 m
        above = self.property_feature({"geometri": {"typ": "yta", "position": {"type": "Polygon", "coordinates": high}}},
                                      values=[self.number("30")], oid="b")
        above["properties"]["vertikalAvgransning"] = vertical.DOWNWARD  # från 6 m
        self.assertEqual(im.parse(collection(below, above)).warnings, [])

    def test_only_the_first_decision_is_imported_and_extra_ones_warn(self):
        decisions = [{"diarienummerKommun": "KS 1"}, {"diarienummerKommun": "KS 2"}]
        with_plan = {**PLAN_FEATURE, "properties": {**PLAN_FEATURE["properties"], "beslutsinformation": decisions}}
        plan = im.parse({"type": "FeatureCollection", "features": [with_plan]})
        self.assertEqual(plan.decision["diarienummerKommun"], "KS 1")
        self.assertTrue(any("bara det första" in w for w in plan.warnings))

    def test_documents_are_read_from_the_plan(self):
        properties = {**PLAN_FEATURE["properties"], "planbeskrivning": {"planbeskrivning": {"namn": "Beskrivning"}},
                     "beslutsinformation": [{"beslutshandling": [
                         {"innehall": ["plankarta", "beslutsprotokoll"], "dokument": {"namn": "Beslut"}}]}],
                     "planeringsunderlag": [{"huvudomrade": "geoteknik", "underlagstyp": "markundersokning",
                                             "underlag": {"namn": "Undersökning"}}]}
        with_plan = {**PLAN_FEATURE, "properties": properties}
        plan = im.parse({"type": "FeatureCollection", "features": [with_plan]})
        rolls = {d["roll"]: d for d in plan.documents}
        self.assertEqual(rolls["planbeskrivning"]["namn"], "Beskrivning")
        self.assertEqual(rolls["beslutshandling"]["innehall"], "plankarta; beslutsprotokoll")
        self.assertEqual(rolls["beslutshandling"]["namn"], "Beslut")
        self.assertEqual(rolls["planeringsunderlag"]["huvudomrade"], "geoteknik")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ControllerImportTests(PlanCase):
    """``PlanController.import_ngp`` (kräver en tom plan och den laddade katalogen)."""

    def setUp(self):
        super().setUp()
        self.errors, self.warnings = [], []
        self.controller = PlanController(self.errors.append, self.warnings.append)
        self.addCleanup(self.controller.detach)

    def test_importing_into_a_plan_that_already_has_an_area_is_refused(self):
        self.add("detaljplan", "MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))")
        pump()
        with self.assertRaises(RuntimeError):
            self.controller.import_ngp(collection(), self.catalog)

    def test_an_unknown_catalog_reference_is_skipped_but_the_area_is_still_created(self):
        summary = self.controller.import_ngp(collection(use_feature(ref="DOES-NOT-EXIST")), self.catalog)
        self.assertEqual((summary.areas, summary.provisions, summary.skipped), (1, 0, 1))
        self.assertTrue(any("hoppades över" in w for w in summary.warnings))
        self.assertEqual(self.layers["anvandning_yta"].featureCount(), 1)
        self.assertEqual(self.layers["bestammelse"].featureCount(), 0)

    def test_a_known_reference_is_assigned_with_its_designation(self):
        entry = pick(self.catalog, "DP_KM_J2")
        summary = self.controller.import_ngp(collection(use_feature(ref=entry.id)), self.catalog)
        self.assertEqual((summary.areas, summary.provisions, summary.skipped), (1, 1, 0))
        self.assertEqual(self.warnings, [])
        (use,) = self.layers["anvandning_yta"].getFeatures()
        self.assertEqual(use["beteckning"], "J")
        self.assertEqual(self.layers["bestammelse"].featureCount(), 1)

    def test_the_plan_attributes_are_written(self):
        self.controller.import_ngp(collection(), self.catalog)
        self.assertEqual(self.controller.plan_values()["namn"], "Kv Väktaren")

    def test_import_starts_an_edit_session_by_itself(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertFalse(self.controller.editing)
        self.controller.import_ngp(collection(), self.catalog)
        self.assertTrue(self.controller.editing)


if __name__ == "__main__":
    unittest.main()
