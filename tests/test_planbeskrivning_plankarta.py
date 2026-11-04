import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plankarta_case import PLAN_ID, make_geopackage, make_json_delivery, make_larkan, make_project  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import geometri as geo  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import plankarta as pk  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_check as ck  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_docx as dx  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import utbyte  # noqa: E402


class ReadOnlyUriTest(unittest.TestCase):
    """Regression: en plan på en nätverkssökväg (servernamn i stället för enhetsbokstav) gav "invalid uri authority" när en ny plan skapades."""

    def test_a_network_path_is_written_with_four_slashes(self):
        from pathlib import PureWindowsPath
        uri = geo.read_only_uri(PureWindowsPath("//admcl01-pro/Desktop$/Lid/plan.gpkg"))
        self.assertTrue(uri.startswith("file:////admcl01-pro/"), uri)
        self.assertTrue(uri.endswith("/plan.gpkg?mode=ro"), uri)

    def test_a_local_path_and_special_characters_still_open(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "min plan #1 (test).db"
            connection = sqlite3.connect(str(path))
            connection.execute("CREATE TABLE t (a)")
            connection.commit()
            connection.close()
            reader = sqlite3.connect(geo.read_only_uri(path), uri=True)
            self.assertEqual(reader.execute("SELECT count(*) FROM t").fetchone()[0], 0)
            reader.close()


class JsonDeliveryTest(unittest.TestCase):
    """Plankartan som en leverans i Lantmäteriets JSON-format i stället för en GeoPackage."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.path = make_json_delivery(self.folder / "leverans.json", motiv={"e1": "Friyta för dagvatten."})

    def tearDown(self):
        self.dir.cleanup()

    def test_it_gives_the_same_provisions_as_the_geopackage_except_for_the_labels(self):
        from_json, = pk.read_plankarta(self.path)
        from_gpkg, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        self.assertEqual((from_json.identitet, from_json.namn), (from_gpkg.identitet, from_gpkg.namn))
        def summary(plan):  # utan nycklarna: de bygger på hur värdena är sparade, och ordningen på beteckningarna
            return sorted((p.text, len(p.refs), plan.kinds[p.key]) for p in plan.provisions)
        self.assertEqual(summary(from_json), summary(from_gpkg))
        self.assertEqual({p.label for p in from_json.provisions}, {""})

    def test_values_are_filled_in_and_motives_are_kept(self):
        plan, = pk.read_json(self.path)
        texts = [p.text for p in plan.provisions]
        self.assertIn("Största byggnadsarea är 30 % av fastighetsarean", texts)
        self.assertIn("Högsta nockhöjd är 14,0 meter", texts)
        area = next(p for p in plan.provisions if p.text.startswith("Största byggnadsarea"))
        self.assertEqual(plan.motiv[area.key], "Friyta för dagvatten.")

    def test_the_map_has_one_shape_per_provision_object(self):
        plan, = pk.read_json(self.path)
        karta = geo.read_karta(plan.kalla, plan.identitet)
        self.assertIsNotNone(karta.border)
        for ids in plan.areas.values():
            for ident in ids:
                self.assertIn(ident, karta.areas)
        use = next(p for p in plan.provisions if p.text == "Park")
        self.assertEqual({karta.layer_of[i] for i in plan.areas[use.key]}, {"anvandning_yta"})
        self.assertIsNotNone(karta.bounds())

    def test_a_file_that_is_not_a_delivery_is_explained(self):
        for name, content, part in (("a.json", "inte json", "går inte att läsa"),
                                    ("b.json", '{"type": "Feature"}', "ingen leverans"),
                                    ("c.json", '{"type": "FeatureCollection", "features": []}', "inget detaljplanobjekt")):
            path = self.folder / name
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(pk.PlankartaError) as context:
                pk.read_plankarta(path)
            self.assertIn(part, str(context.exception))
        self.assertEqual(geo.read_karta(self.folder / "a.json").bounds(), None)

    def test_the_session_loads_it_like_any_other_plankarta(self):
        from rita_detaljplan.planbeskrivning.pbapp import session as ss
        session = ss.Session(ss.Store.memory())
        session.load_plankarta(self.path)
        self.assertEqual(session.plan.namn, "Detaljplan för kv. Lärkan")
        self.assertTrue(session.karta.areas)


class GeoPackageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_the_same_provision_on_several_areas_is_one_provision_with_every_object(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        self.assertEqual((plan.identitet, plan.namn, plan.beteckning), (PLAN_ID, "Detaljplan för kv. Lärkan", "1485-P2026/3"))
        self.assertEqual(len(plan.provisions), 12)
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(len(b.refs), 3)
        self.assertEqual(len(set(b.refs)), 3)
        self.assertEqual(plan.kinds[b.key], "anvandning_yta")

    def test_values_are_filled_into_the_formulation(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        texts = {p.label: p.text for p in plan.provisions}
        self.assertEqual(texts["e1"], "Största byggnadsarea är 30 % av fastighetsarean")
        self.assertEqual(texts["h1"], "Högsta nockhöjd är 14,0 meter")

    def test_uses_come_before_properties(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        kinds = [plan.kinds[p.key] for p in plan.provisions]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "anvandning_yta"))

    def test_motives_already_on_the_map_are_read(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg", motiv={"B": "Bostäder behövs."}))
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(plan.motiv[b.key], "Bostäder behövs.")

    def test_a_file_that_is_not_a_plan_is_explained(self):
        other = self.folder / "annat.gpkg"
        other.write_bytes(b"inte en databas" * 100)
        with self.assertRaises(pk.PlankartaError):
            pk.read_geopackage(other)
        with self.assertRaisesRegex(pk.PlankartaError, "finns inte"):
            pk.read_geopackage(self.folder / "saknas.gpkg")


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        make_geopackage(self.folder / "kv_Larkan.gpkg")

    def tearDown(self):
        self.dir.cleanup()

    def test_a_qgz_project_points_to_its_geopackage(self):
        project = make_project(self.folder / "plan.qgz", "kv_Larkan.gpkg")
        self.assertEqual(pk.geopackages_in_project(project), [(self.folder / "kv_Larkan.gpkg").resolve()])
        plan, = pk.read_plankarta(project)
        self.assertEqual(plan.identitet, PLAN_ID)

    def test_a_qgs_project_works_too(self):
        plan, = pk.read_plankarta(make_project(self.folder / "plan.qgs", "kv_Larkan.gpkg"))
        self.assertEqual(len(plan.provisions), 12)

    def test_a_plan_in_postgis_is_explained(self):
        project = make_project(self.folder / "plan.qgz", "kv_Larkan.gpkg", provider="postgres")
        with self.assertRaisesRegex(pk.PlankartaError, "PostGIS"):
            pk.read_plankarta(project)

    def test_a_missing_geopackage_is_explained(self):
        project = make_project(self.folder / "plan.qgz", "flyttad.gpkg")
        with self.assertRaisesRegex(pk.PlankartaError, "hittades inte"):
            pk.read_plankarta(project)


class KartaTest(unittest.TestCase):
    def test_the_areas_and_the_plan_border_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            gpkg = make_geopackage(Path(folder) / "plan.gpkg")
            plan, = pk.read_geopackage(gpkg)
            karta = geo.read_karta(gpkg, plan.identitet)
        self.assertEqual(len(karta.areas), 6)
        self.assertIsNotNone(karta.border)
        x0, y0, x1, y1 = karta.bounds()
        self.assertAlmostEqual(x1 - x0, 288)
        self.assertAlmostEqual(y1 - y0, 188)
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(sorted(karta.labels[a] for a in plan.areas[b.key]), ["B", "B", "B"])

    def test_a_plan_without_geometry_gives_an_empty_map(self):
        with tempfile.TemporaryDirectory() as folder:
            karta = geo.read_karta(make_geopackage(Path(folder) / "plan.gpkg", geometry=False))
        self.assertEqual((karta.areas, karta.border, karta.bounds()), ({}, None, None))

    def test_z_values_and_big_endian_are_read(self):
        import struct
        ring = [(0, 0, 5), (1, 0, 5), (1, 1, 5), (0, 0, 5)]
        wkb = struct.pack(">BII", 0, 1003, 1) + struct.pack(">I", 4) + b"".join(struct.pack(">ddd", *p) for p in ring)
        shape = geo.parse_gpkg_geometry(b"GP\x00\x00" + struct.pack("<i", 3006) + wkb)
        self.assertEqual(shape.parts, [[(0, 0), (1, 0), (1, 1), (0, 0)]])
        self.assertIsNone(geo.parse_gpkg_geometry(b"inte"))

    def test_a_crafted_geometry_is_refused_quickly_instead_of_exhausting_memory(self):
        import struct
        import time
        claims_four_billion_points = b"\x01" + struct.pack("<II", 2, 0xFFFFFFFF)
        nested_collections = (b"\x01" + struct.pack("<II", 7, 1)) * 5000
        started = time.monotonic()
        self.assertIsNone(geo.parse_wkb(claims_four_billion_points))
        self.assertIsNone(geo.parse_wkb(nested_collections))
        self.assertLess(time.monotonic() - started, 2)


class ExampleTest(unittest.TestCase):
    """Hela flödet med exemplet kv. Lärkan: läsa plankartan, analysera dokumentet, skriva en leveranskopia."""

    def test_the_example_is_analysed_and_tagged(self):
        with tempfile.TemporaryDirectory() as folder:
            files = make_larkan(Path(folder))
            plan, = pk.read_plankarta(files["qgz"])
            analysis = dx.analyse(files["docx"], plan.provisions)
            matched = {next(p.label for p in plan.provisions if p.key == m.key) for m in analysis.motives if m.key}
            self.assertTrue({"B", "GATA", "PARK", "e1", "h1", "b1", "n1", "r1"} <= matched, matched)
            review = [s for s in analysis.sections if s.status in dx.NEEDS_REVIEW]
            self.assertTrue(review, "exemplet ska ha något att granska")
            result = dx.tag_docx(analysis, Path(folder) / "ut.docx", plan.identitet, "0.1.0",
                                 software="Planbeskrivning Taggning")
            self.assertGreater(result.avsnitt, 10)
            again = dx.analyse(Path(folder) / "ut.docx", plan.provisions)
            self.assertEqual(again.previous.programvara, "Planbeskrivning Taggning")
            self.assertIsInstance(ck.check(analysis), list)

            data = utbyte.build(analysis, plan.identitet, "Planbeskrivning Taggning")
            self.assertTrue(data["syfte"].startswith("Syftet med detaljplanen"))
            by_label = {m["beteckning"]: m for m in data["motiv"]}
            self.assertIn("Lärkvägen förlängs", by_label["GATA"]["motiv"])
            self.assertEqual(len(by_label["B"]["objekt"]), 3)
            back = utbyte.read(utbyte.write(Path(folder) / "motiv.json", data))
            self.assertEqual(back["motiv"], data["motiv"])
            with self.assertRaises(utbyte.UtbyteError):
                utbyte.read(files["gpkg"])


if __name__ == "__main__":
    unittest.main()
