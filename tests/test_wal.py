"""WAL-filen: en kopia av bara .gpkg-filen ska vara komplett efter att planen sparats."""
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PLAN, PlanCase, pump  # noqa: E402

if HAVE_QGIS:
    from unittest import mock

    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core import geopackage


def count_rows(path, table="detaljplan") -> int:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    finally:
        con.close()


class CheckpointTests(unittest.TestCase):
    """Ren SQLite (som QGIS håller en GeoPackage): en öppen anslutning håller filen i WAL-läge."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.db = self.dir / "plan.gpkg"
        self.qgis = sqlite3.connect(str(self.db))  # "QGIS": håller filen öppen hela tiden
        self.addCleanup(self.qgis.close)
        self.qgis.execute("PRAGMA journal_mode=WAL")
        self.qgis.execute("CREATE TABLE t (x INTEGER)")
        self.qgis.commit()

    def copy_of_gpkg_only(self) -> Path:
        copy = self.dir / "kopia.gpkg"
        shutil.copyfile(self.db, copy)
        return copy

    def test_without_a_checkpoint_the_latest_changes_are_missing_from_a_copy(self):
        self.qgis.execute("INSERT INTO t VALUES (1)")
        self.qgis.commit()
        self.assertTrue((self.dir / "plan.gpkg-wal").exists())
        copy = self.copy_of_gpkg_only()
        with self.assertRaises(sqlite3.DatabaseError):  # tabellen ligger själv i -wal-filen
            count_rows(copy, "t")

    def test_after_a_checkpoint_a_copy_of_the_gpkg_alone_is_complete(self):
        self.qgis.execute("INSERT INTO t VALUES (1)")
        self.qgis.commit()
        self.assertTrue(geopackage.checkpoint(self.db))
        self.assertEqual(count_rows(self.copy_of_gpkg_only(), "t"), 1)

    def test_the_checkpoint_changes_nothing_in_the_plan_and_can_be_repeated(self):
        self.qgis.execute("INSERT INTO t VALUES (1)")
        self.qgis.commit()
        for _ in range(3):
            self.assertTrue(geopackage.checkpoint(self.db))
        self.assertEqual(self.qgis.execute("SELECT x FROM t").fetchall(), [(1,)])

    def test_a_reader_in_the_middle_of_a_read_does_not_make_it_fail(self):
        self.qgis.execute("INSERT INTO t VALUES (1)")
        self.qgis.commit()
        reader = sqlite3.connect(str(self.db))
        self.addCleanup(reader.close)
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM t").fetchall()  # läsaren håller en ögonblicksbild
        self.qgis.execute("INSERT INTO t VALUES (2)")
        self.qgis.commit()
        geopackage.checkpoint(self.db)  # får inte kasta, hur det än går
        self.assertEqual(self.qgis.execute("SELECT count(*) FROM t").fetchone()[0], 2)

    def test_a_file_that_is_not_in_wal_mode_needs_nothing(self):
        plain = self.dir / "vanlig.gpkg"
        con = sqlite3.connect(str(plain))
        con.execute("CREATE TABLE t (x INTEGER)")
        con.commit()
        con.close()
        self.assertTrue(geopackage.checkpoint(plain))

    def test_a_missing_file_is_not_created(self):
        missing = self.dir / "finns_inte.gpkg"
        self.assertFalse(geopackage.checkpoint(missing))
        self.assertFalse(missing.exists())

    def test_something_that_is_not_a_database_gives_false_not_an_error(self):
        junk = self.dir / "skräp.gpkg"
        junk.write_bytes(b"this is not a database" * 100)
        self.assertFalse(geopackage.checkpoint(junk))


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class SavingTests(PlanCase):
    """Med QGIS: när ändringar sparats ska en kopia av bara .gpkg-filen innehålla dem."""

    def setUp(self):
        super().setUp()
        self.controller = PlanController(mock.Mock(), mock.Mock(), open_form=mock.Mock())
        self.addCleanup(self.controller.detach)

    def copy_of_gpkg_only(self) -> Path:
        copy = self.dir / "kopia.gpkg"
        shutil.copyfile(self.gpkg, copy)
        return copy

    def edit_only_the_plan_layer(self):
        """Bara planlagret redigeras (då blir ändringen kvar i -wal-filen även när redigeringen stoppats)."""
        for table, layer in self.layers.items():
            if table != "detaljplan" and layer.isEditable():
                layer.rollBack()
        self.controller.attach()
        self.add("detaljplan", PLAN)

    def test_a_copy_of_the_gpkg_alone_has_the_plan_that_was_just_saved(self):
        self.edit_only_the_plan_layer()
        self.assertTrue(self.layers["detaljplan"].commitChanges())
        pump()
        self.assertEqual(count_rows(self.copy_of_gpkg_only()), 1)

    def test_the_same_when_saving_continues_the_edit_session(self):
        self.edit_only_the_plan_layer()
        self.assertTrue(self.layers["detaljplan"].commitChanges(False))  # QGIS egen spara-knapp
        pump()
        self.assertEqual(count_rows(self.copy_of_gpkg_only()), 1)

    def test_the_checkpoint_is_made_once_for_all_layers_saved_together(self):
        self.controller.attach()
        self.add("detaljplan", PLAN)
        with mock.patch.object(geopackage, "checkpoint", wraps=geopackage.checkpoint) as checkpoint:
            self.controller.stop_editing(save=True)
            pump()
        self.assertEqual(checkpoint.call_count, 1)
        self.assertEqual(Path(checkpoint.call_args.args[0]).resolve(), Path(self.gpkg).resolve())

    def test_nothing_happens_after_the_controller_has_been_detached(self):
        self.controller.attach()
        self.add("detaljplan", PLAN)
        self.controller.stop_editing(save=True)
        self.controller.detach()
        with mock.patch.object(geopackage, "checkpoint") as checkpoint:
            pump()
        checkpoint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
