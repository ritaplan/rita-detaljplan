import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plankarta_case import make_json_delivery, make_larkan  # noqa: E402
from rita_detaljplan.planbeskrivning.pbapp import session as ss  # noqa: E402
from rita_detaljplan.planbeskrivning.pbweb.api import Webb  # noqa: E402


class WebbTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.files = make_larkan(self.folder)
        self.web = Webb()

    def tearDown(self):
        self.dir.cleanup()

    def open(self, plankarta="gpkg") -> dict:
        self.assertEqual(self.web.las_plankarta(str(self.files[plankarta])), {"ok": True})
        self.assertEqual(self.web.las_planbeskrivning(str(self.files["docx"])), {"ok": True})
        return self.web.tillstand()

    def test_the_state_is_plain_json_and_has_what_the_four_steps_show(self):
        state = self.open()
        json.dumps(state)  # allt ska gå att skicka till sidan
        self.assertTrue(state["klar"])
        self.assertEqual((state["plan"]["bestammelser"], state["plan"]["ytor"]), (12, 6))
        self.assertIn("<svg", state["plan"]["karta"])
        self.assertEqual(state["dokument"]["namn"], "Planbeskrivning_kv_Larkan.docx")
        self.assertTrue(state["avsnitt"] and state["motiv"] and state["bestammelser"] and state["fynd"])
        self.assertEqual(state["namn"]["leverans"], "Planbeskrivning_kv_Larkan_leverans.docx")

    def test_it_is_not_ready_until_both_files_are_loaded(self):
        self.assertFalse(self.web.tillstand()["klar"])
        self.web.las_plankarta(str(self.files["gpkg"]))
        state = self.web.tillstand()
        self.assertEqual((state["klar"], state["plan"]["bestammelser"], state["dokument"]), (False, 12, None))
        self.assertNotIn("avsnitt", state)

    def test_a_json_delivery_works_as_plankarta(self):
        path = make_json_delivery(self.folder / "leverans.json")
        self.files["json"] = path
        state = self.open("json")
        self.assertEqual(state["plan"]["bestammelser"], 12)
        self.assertEqual(state["plan"]["ytor"], 23)

    def test_files_that_cannot_be_read_give_an_error_not_an_exception(self):
        projekt = self.web.las_plankarta(str(self.files["qgz"]))
        self.assertIn("GeoPackage", projekt["fel"])
        trasig = self.folder / "trasig.docx"
        trasig.write_bytes(b"inte en zip")
        self.assertIn("fel", self.web.las_planbeskrivning(str(trasig)))
        self.assertIn("fel", self.web.las_plankarta(str(self.folder / "finns_inte.gpkg")))

    def test_choosing_a_group_changes_the_section_and_marks_it_reviewed(self):
        state = self.open()
        section = next(s for s in state["avsnitt"] if s["status"] in (ss.EGEN, ss.OSAKER, ss.SAKNAS))
        grupp = next(iter(Webb.alternativ()["Planeringsförutsättningar"]))
        self.web.valj_indelning(section["nyckel"], "Planeringsförutsättningar", grupp, "")
        after = next(s for s in self.web.tillstand()["avsnitt"] if s["nyckel"] == section["nyckel"])
        self.assertEqual((after["tema"], after["grupp"], after["status"]), ("Planeringsförutsättningar", grupp, ss.GRANSKAD))

    def test_skipping_a_section_and_taking_it_back(self):
        state = self.open()
        key = state["avsnitt"][0]["nyckel"]
        self.web.hoppa_over(key)
        self.assertEqual(next(s for s in self.web.tillstand()["avsnitt"] if s["nyckel"] == key)["status"], ss.HOPPAS)
        self.web.hoppa_over(key, False)
        self.assertNotEqual(next(s for s in self.web.tillstand()["avsnitt"] if s["nyckel"] == key)["status"], ss.HOPPAS)

    def test_linking_a_motive_by_hand_and_removing_the_link(self):
        state = self.open()
        okopplat = next(m for m in state["motiv"] if m["status"] == "ej")
        provision = next(p for p in state["bestammelser"] if not p["har_motiv"] and not p["tekniskt"])
        self.assertEqual(self.web.koppla_motiv(okopplat["signatur"], provision["nyckel"]), {"ok": True})
        after = next(m for m in self.web.tillstand()["motiv"] if m["signatur"] == okopplat["signatur"])
        self.assertEqual((after["status"], after["bestammelse"]), ("kopplat", provision["nyckel"]))
        self.web.koppla_motiv(okopplat["signatur"], None)
        again = next(m for m in self.web.tillstand()["motiv"] if m["signatur"] == okopplat["signatur"])
        self.assertEqual((again["status"], again["bestammelse"]), ("ej", None))
        self.assertIn("fel", self.web.koppla_motiv(okopplat["signatur"], "finns inte"))
        self.assertIn("fel", self.web.koppla_motiv("finns inte", None))

    def test_the_copies_are_written_and_the_review_copy_has_comments(self):
        self.open()
        leverans = self.web.spara_kopia(str(self.folder / "lev.docx"))
        granskning = self.web.spara_kopia(str(self.folder / "gran.docx"), True)
        self.assertTrue(leverans["ok"] and leverans["avsnitt"] > 0 and leverans["kommentarer"] == 0)
        self.assertGreater(granskning["kommentarer"], 0)
        with zipfile.ZipFile(self.folder / "lev.docx") as z:
            self.assertIsNone(z.testzip())
        original = self.web.spara_kopia(str(self.files["docx"]))  # får aldrig skriva över originalet
        self.assertIn("annat namn", original["fel"])

    def test_the_overview_and_the_map_highlight(self):
        state = self.open()
        csv = self.web.oversikt_csv()
        self.assertIn("Syfte", csv["text"])
        park = next(p for p in state["bestammelser"] if p["text"] == "Park")
        self.assertIn('class="anv mark"', self.web.karta(park["nyckel"]))
        self.assertNotIn(" mark", self.web.karta())

    def test_the_choices_are_remembered_through_the_store(self):
        data: dict = {}
        store = ss.Store(data.get, data.__setitem__)
        web = Webb(store)
        web.las_plankarta(str(self.files["gpkg"]))
        web.las_planbeskrivning(str(self.files["docx"]))
        section = next(s for s in web.tillstand()["avsnitt"] if s["status"] in (ss.EGEN, ss.OSAKER, ss.SAKNAS))
        web.valj_indelning(section["nyckel"], "Planeringsförutsättningar", "Kommunala", "")
        again = Webb(store)
        again.las_plankarta(str(self.files["gpkg"]))
        again.las_planbeskrivning(str(self.files["docx"]))
        after = next(s for s in again.tillstand()["avsnitt"] if s["nyckel"] == section["nyckel"])
        self.assertEqual(after["status"], ss.GRANSKAD)


if __name__ == "__main__":
    unittest.main()
