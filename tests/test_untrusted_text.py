"""Namn och text som kommer utifrån, till exempel ur en delad databas: de får inte styra var filer hamnar, inte tolkas
som formaterad text (då kan Qt läsa in en bildfil som texten pekar på) och inte bryta SQL-blocken."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from qgis.core import Qgis
    from qgis.gui import QgsMessageBar
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QLabel, QMessageBox, QTextEdit
    from qgis_app import get_app
    from rita_detaljplan.core import checkout, storage, transfer
    from rita_detaljplan.gui import database_manager_dialog as manager
    from rita_detaljplan.gui.messages import push
    from rita_detaljplan.gui.richtext import as_text, plain
    from test_postgis import FakeConnection
    HAVE_QGIS = True
except ImportError:  # pragma: no cover
    HAVE_QGIS = False

PICTURE = "<img src='file:////server/delad/bild.png'>"
BAD_NAMES = ("..\\..\\utanfor", "../../utanfor", "C:\\temp\\annan", "\\\\server\\delad\\plan", "a:b*c?", " .. ")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class FileNameTests(unittest.TestCase):
    def setUp(self):
        get_app()
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name) / "vald"
        self.folder.mkdir()

    def plan(self, schema="dp_a", plan_id="kv_norr"):
        return storage.PostgisStorage("min databas", schema, plan_id, object())

    def assert_inside(self, path: Path):
        self.assertEqual(path.resolve().parent, self.folder.resolve(), path)

    def test_the_names_the_plugin_creates_are_unchanged(self):
        for name in ("kv_norr", "dp_2026_14", "Kv Norr åäö"):
            self.assertEqual(storage.file_name(name), name)

    def test_an_export_stays_in_the_chosen_folder_whatever_the_database_calls_the_plan(self):
        for bad in BAD_NAMES:
            for suffix in (".gpkg", ".json"):
                _plan, path = transfer.unique_export_paths(self.folder, [self.plan(plan_id=bad)], suffix)[0]
                self.assert_inside(path)
                self.assertTrue(path.name.endswith(suffix), path.name)

    def test_the_schema_name_is_made_harmless_when_two_plans_share_an_id(self):
        plans = [self.plan(schema="..\\..\\x", plan_id="p"), self.plan(schema="dp_b", plan_id="p")]
        for _plan, path in transfer.unique_export_paths(self.folder, plans):
            self.assert_inside(path)

    def test_the_local_copy_of_a_checked_out_plan_stays_in_its_folder(self):
        lock = checkout.new_lock()
        for bad in BAD_NAMES:
            self.assert_inside(checkout.copy_path(self.plan(schema=bad, plan_id=bad), lock, self.folder))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SqlBlockTests(unittest.TestCase):
    def test_a_normal_block_looks_as_before(self):
        self.assertEqual(storage.do_block("SELECT 1;"), "DO $dp$ BEGIN SELECT 1; END $dp$")

    def test_the_dollar_quote_never_occurs_in_the_content(self):
        block = storage.do_block("INSERT INTO t VALUES ('skäl: $dp$ och $dp1$');")
        self.assertTrue(block.startswith("DO $dp2$ BEGIN ") and block.endswith(" END $dp2$"), block)

    def test_a_protection_reason_and_a_plan_id_cannot_end_the_block(self):
        conn = FakeConnection(plugin_schemas=["dp_a"])
        conn.plan_meta["dp_a"] = {"p": {"epsg": "3006"}}
        plan = storage.PostgisStorage("a", "dp_a", "p", conn)
        checkout.protect(plan, "$dp$")
        self.assertIn("DO $dp1$ BEGIN", [s for s in conn.sql if s.startswith("DO ")][-1])
        self.assertTrue(transfer.delete_sql("dp_a", "x$dp$").startswith("DO $dp1$ BEGIN "))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class TextTests(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_text_without_markup_is_left_alone(self):
        self.assertEqual(as_text("Utcheckad av anna på DATOR-1\nrad två"), "Utcheckad av anna på DATOR-1\nrad två")

    def test_markup_is_shown_literally(self):
        shown = as_text(f"laga kraft {PICTURE} & mer")
        self.assertNotIn("<img", shown)
        self.assertIn("&lt;img", shown)
        self.assertIn("&amp; mer", shown)

    def test_a_plain_label_and_message_box_do_not_read_markup(self):
        for widget in (QLabel(), QMessageBox()):
            self.assertEqual(plain(widget).textFormat(), Qt.TextFormat.PlainText)

    def test_the_message_bar_shows_the_text_as_it_is(self):
        for text in (f"Fel i planen {PICTURE}", "Bostäder & handel", "a < b\nrad två", "Vanlig text"):
            bar = QgsMessageBar()
            push(bar, "Rubrik", text, Qgis.MessageLevel.Warning)
            shown = bar.findChildren(QTextEdit)[0].toPlainText()
            self.assertIn(text.split("\n")[0], shown)
            self.assertNotIn("\ufffc", shown)  # tecknet för en inläst bild

    def test_the_database_manager_never_formats_text_from_the_database(self):
        conn = FakeConnection(plugin_schemas=["dp_a"])
        lock = checkout.new_lock()
        conn.plan_meta["dp_a"] = {
            "p1": {"checkout": checkout.Lock(lock.token, PICTURE, "DATOR", "2026-11-25T10:00").to_json()},
            "p2": {"skrivskydd": f'{{"user": "anna", "host": "D", "since": "", "reason": "{PICTURE}"}}'}}
        conn.plan_rows["dp_a"] = [["p1", PICTURE, PICTURE, "Kommun", PICTURE, "samråd", "detaljplan"],
                                  ["p2", "Två", "2", "Kommun", "Syfte", "antagen", "detaljplan"]]
        dialog = manager.DatabaseManagerDialog(None, {"a": conn})
        self.addCleanup(dialog.deleteLater)
        tips = [dialog.model.item(r, c).toolTip() for r in range(dialog.model.rowCount())
                for c in range(dialog.model.columnCount())]
        self.assertTrue(any("&lt;img" in tip for tip in tips))
        self.assertEqual([tip for tip in tips if "<img" in tip], [])
        for row in range(dialog.proxy.rowCount()):
            dialog.table.selectRow(row)
            for label in dialog.findChildren(QLabel):
                if "<img" in label.text():
                    self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText, label.text())


if __name__ == "__main__":
    unittest.main()
