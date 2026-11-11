"""Flytta planer mellan en GeoPackage och en databas: importera en fil, exportera en plan, och databashanterarens knappar
(kräver QGIS).

Ingen riktig databas används (som i test_checkout): en låtsasanslutning tar emot och tolkar den SQL som pluginet skickar.
Att importens SQL fungerar mot en riktig PostgreSQL med PostGIS är därför inte provat här, men den är samma SQL som
incheckningen och skapandet av en ny plan använder."""
import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PlanCase  # noqa: E402

if HAVE_QGIS:
    from osgeo import ogr
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import QItemSelectionModel
    from rita_detaljplan import json_transfer
    from rita_detaljplan.core import checkout as co
    from rita_detaljplan.core import export_ngp, geopackage, model, storage, transfer
    from rita_detaljplan.core.project import find_layer
    from rita_detaljplan.gui import database_manager_dialog as manager
    from rita_detaljplan.gui.database_manager_dialog import ROW_ROLE, DatabaseManagerDialog
    from rita_detaljplan.gui.copy_plan_dialog import CopyPlanDialog, CopyValues
    from rita_detaljplan.gui.import_plan_dialog import JSON, ImportPlanDialog, ImportValues
    from rita_detaljplan.core.plan_overview import PlanRow
    from test_checkout import CheckoutCase, other_lock
    from test_export import ExportCase
    from test_postgis import FakeConnection


class ImportConnection(FakeConnection):
    """Låtsasdatabas som också tar emot låset, incheckningens SQL, radräkningen och borttagningen vid misslyckad import."""

    def __init__(self, counts=None, **kwargs):
        super().__init__(**kwargs)
        self.counts = counts  # tabell -> antal rader som databasen svarar att den har; None: räknas ur SQL:en
        self.inserted = {}
        self.checkins = []
        self.deleted = []
        self.checkin_error = None

    def executeSql(self, sql):
        if sql.startswith("DO $dp$ BEGIN LOCK TABLE"):
            self.sql.append(sql)
            schema = re.search(r'LOCK TABLE "(\w+)"\."dp_meta"', sql).group(1)
            plan_id, lock = re.search(r"VALUES \('([^']*)', 'checkout', '(.*)'\); END IF", sql).groups()
            self.plan_meta[schema][plan_id]["checkout"] = lock.replace("''", "'")
            return []
        if sql.startswith("DO $dp"):  # incheckningens SQL
            self.sql.append(sql)
            if self.checkin_error:
                raise RuntimeError(self.checkin_error)
            schema, plan_id = re.search(r'FROM "(\w+)"\."dp_meta" WHERE "plan" = \'([^\']*)\'', sql).groups()
            self.plan_meta[schema][plan_id].pop("checkout")
            self.checkins.append(sql)
            for part in sql.split("INSERT INTO ")[1:]:  # varje rad börjar med planens id: ('plan', ...
                table = re.match(r'"\w+"\."(\w+)"', part).group(1)
                self.inserted[table] = self.inserted.get(table, 0) + part.count(f"('{plan_id}', ")
            return []
        match = re.match(r'SELECT count\(\*\) FROM "(\w+)"\."(\w+)" WHERE "plan" = \'([^\']*)\'', sql)
        if match:
            self.sql.append(sql)
            counts = self.inserted if self.counts is None else self.counts
            return [[counts.get(match.group(2), 0)]]
        match = re.match(r'DELETE FROM "(\w+)"\."(\w+)" WHERE "plan" = \'([^\']*)\'', sql)
        if match:
            self.sql.append(sql)
            self.deleted.append(sql)
            schema, table, plan_id = match.groups()
            if table == model.META_TABLE:
                self.plan_meta.get(schema, {}).pop(plan_id, None)
            return []
        return super().executeSql(sql)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ImportTests(ExportCase):
    """Importerar den färdiga planen i ExportCase (en GeoPackage) till låtsasdatabasen."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        self.counts = {d.name: find_layer(QgsProject.instance(), d.name).featureCount() for d in model.LAYERS}
        self.conn = ImportConnection(self.counts)
        self.source_meta = geopackage.read_meta(self.gpkg)

    def existing_schema(self, epsg=None):
        self.conn.schema_meta["dp_new"] = {"schema_version": str(model.SCHEMA_VERSION),
                                            "epsg": str(epsg or self.source_meta["epsg"])}
        self.conn.plugin_schemas.append("dp_new")

    def copy_of_source(self, name="kopia.gpkg"):
        return geopackage.snapshot(self.gpkg, self.dir / name)

    def import_it(self, path=None, plan_id="ny_plan"):
        return transfer.import_plan(path or self.gpkg, "db", "dp_new", plan_id, self.conn)

    def test_the_plan_is_added_to_the_schema_with_its_details_and_every_row(self):
        result = self.import_it()
        meta = self.conn.plan_meta["dp_new"]["ny_plan"]
        for key, value in self.source_meta.items():
            if key not in ("schema_version", "spec_version", "epsg"):
                self.assertEqual(meta.get(key), value, key)
        self.assertEqual(meta["spec_version"], model.SPEC_VERSION)
        self.assertEqual(self.conn.schema_meta["dp_new"]["epsg"], self.source_meta["epsg"], "schemat får planens koordinatsystem")
        self.assertEqual(result.counts, self.counts)
        self.assertEqual(result.total, sum(self.counts.values()))
        self.assertGreater(self.counts["anvandning_yta"], 0, "planen har innehåll")
        self.assertEqual(result.plan, storage.PostgisStorage("db", "dp_new", "ny_plan"))
        self.assertEqual(len(self.conn.checkins), 1, "alla rader skrivs i en enda transaktion")
        sql = self.conn.checkins[0]
        for layer_def in model.LAYERS:
            self.assertIn(f'DELETE FROM "dp_new"."{layer_def.name}" WHERE "plan" = \'ny_plan\'', sql)
        self.assertIn("ST_Multi(ST_GeomFromText(", sql)

    def test_the_lock_taken_for_the_import_is_released_and_nothing_is_left_checked_out(self):
        self.import_it()
        self.assertNotIn("checkout", self.conn.plan_meta["dp_new"]["ny_plan"])
        self.assertEqual(self.conn.deleted, [])

    def test_checkout_details_of_a_local_copy_are_not_taken_into_the_database(self):
        copy = self.copy_of_source()
        con = sqlite3.connect(str(copy))
        con.executemany(f'INSERT INTO "{model.META_TABLE}" (key, value) VALUES (?, ?)',
                        [("checkout_token", "abc"), ("checkout_schema", "annat"), ("checkout", "{}")])
        con.commit()
        con.close()
        self.import_it(copy)
        meta = self.conn.plan_meta["dp_new"]["ny_plan"]
        self.assertFalse([key for key in meta if key.startswith("checkout")])

    def test_a_protection_in_the_file_does_not_make_the_new_plan_protected(self):
        copy = self.copy_of_source()
        con = sqlite3.connect(str(copy))
        con.execute(f'INSERT INTO "{model.META_TABLE}" (key, value) VALUES (?, ?)', ("skrivskydd", "{}"))
        con.commit()
        con.close()
        self.import_it(copy)
        self.assertNotIn("skrivskydd", self.conn.plan_meta["dp_new"]["ny_plan"])

    def test_a_row_count_that_does_not_match_removes_the_plan_again(self):
        self.conn.counts = {**self.counts, "detaljplan": self.counts["detaljplan"] + 1}
        with self.assertRaisesRegex(transfer.TransferError, "inte komplett.*detaljplan"):
            self.import_it()
        self.assertNotIn("ny_plan", self.conn.plan_meta["dp_new"])
        self.assertEqual(len(self.conn.deleted), len(model.LAYERS) + 1, "alla tabeller och planens uppgifter")

    def test_a_database_error_while_writing_removes_the_plan_again(self):
        self.conn.checkin_error = "disken är full"
        with self.assertRaisesRegex(storage.PostgisError, "disken är full"):
            self.import_it()
        self.assertNotIn("ny_plan", self.conn.plan_meta["dp_new"])
        self.assertEqual(self.conn.checkins, [])

    def test_a_plan_id_that_is_taken_is_refused_and_the_existing_plan_is_left_alone(self):
        self.existing_schema()
        self.conn.plan_meta["dp_new"] = {"ny_plan": {"kommun": "Annan"}}
        with self.assertRaisesRegex(storage.PostgisError, "finns redan en plan"):
            self.import_it()
        self.assertEqual(self.conn.plan_meta["dp_new"]["ny_plan"], {"kommun": "Annan"})
        self.assertEqual(self.conn.deleted, [])
        self.assertEqual(self.conn.checkins, [])

    def test_a_schema_with_another_coordinate_system_is_refused_without_changes(self):
        other = 3007 if self.source_meta["epsg"] != "3007" else 3006
        self.existing_schema(other)
        with self.assertRaisesRegex(storage.PostgisError, f"EPSG:{other}"):
            self.import_it()
        self.assertEqual(self.conn.deleted, [])
        self.assertNotIn("ny_plan", self.conn.plan_meta.get("dp_new", {}))

    def test_a_file_that_is_no_plan_is_refused_before_the_database_is_touched(self):
        text = self.dir / "inte_en_plan.gpkg"
        text.write_text("detta är ingen databas")
        for path in (text, self.dir / "finns_inte.gpkg"):
            with self.assertRaisesRegex(transfer.TransferError, "ingen detaljplan"):
                self.import_it(path)
        self.assertEqual(self.conn.sql, [])

    def test_a_plan_made_with_a_newer_version_is_refused(self):
        copy = self.copy_of_source()
        con = sqlite3.connect(str(copy))
        con.execute(f'UPDATE "{model.META_TABLE}" SET value = ? WHERE key = ?', (str(model.SCHEMA_VERSION + 1), "schema_version"))
        con.commit()
        con.close()
        with self.assertRaisesRegex(transfer.TransferError, "nyare version"):
            self.import_it(copy)
        self.assertEqual(self.conn.sql, [])

    def test_an_older_plan_without_the_tables_that_came_later_is_imported_with_those_empty(self):
        copy = self.copy_of_source()
        ds = ogr.Open(str(copy), 1)
        for index in range(ds.GetLayerCount()):
            if ds.GetLayerByIndex(index).GetName() == model.EGENSKAP_PUNKT.name:
                ds.DeleteLayer(index)
                break
        ds = None
        con = sqlite3.connect(str(copy))
        con.execute(f'UPDATE "{model.META_TABLE}" SET value = ? WHERE key = ?', ("9", "schema_version"))
        con.commit()
        con.close()
        result = self.import_it(copy)
        self.assertEqual(result.counts[model.EGENSKAP_PUNKT.name], 0)
        self.assertEqual(result.counts["anvandning_yta"], self.counts["anvandning_yta"])

    def test_the_same_table_missing_from_a_current_plan_is_an_error(self):
        copy = self.copy_of_source()
        ds = ogr.Open(str(copy), 1)
        for index in range(ds.GetLayerCount()):
            if ds.GetLayerByIndex(index).GetName() == model.EGENSKAP_PUNKT.name:
                ds.DeleteLayer(index)
                break
        ds = None
        with self.assertRaisesRegex(transfer.TransferError, "saknas"):
            self.import_it(copy)
        self.assertEqual(self.conn.sql, [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ExportTests(CheckoutCase):
    """Exporterar den färdiga planen (som låtsasdatabasens plan) till en GeoPackage."""

    def test_a_plan_is_saved_as_a_new_geopackage_with_every_row(self):
        path = transfer.export_plan(self.plan, self.dir / "ut.gpkg")
        meta = geopackage.read_meta(path)
        source = geopackage.read_meta(self.gpkg)
        self.assertEqual(meta["schema_version"], str(model.SCHEMA_VERSION))
        self.assertEqual(meta["epsg"], source["epsg"])
        self.assertEqual(meta["kommun"], source["kommun"])
        copy = storage.GeoPackageStorage(path)
        for layer_def in model.LAYERS:
            self.assertEqual(copy.make_layer(layer_def).featureCount(), self.counts()[layer_def.name], layer_def.name)
        self.assertGreater(self.counts()["anvandning_yta"], 0)

    def test_the_file_is_complete_without_its_wal_file(self):
        path = transfer.export_plan(self.plan, self.dir / "ut.gpkg")
        self.assertFalse(Path(str(path) + "-wal").exists() and Path(str(path) + "-wal").stat().st_size > 0)

    def test_a_plan_checked_out_by_someone_else_is_exported_as_it_is_in_the_database_and_stays_locked(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        path = transfer.export_plan(self.plan, self.dir / "ut.gpkg")
        self.assertFalse([key for key in geopackage.read_meta(path) if key.startswith("checkout")])
        self.assertEqual(co.read_lock(self.plan), other_lock())

    def test_a_protected_plan_can_be_exported_and_the_file_carries_no_protection(self):
        self.conn.meta["skrivskydd"] = co.Protection("anna", "ANNAS-DATOR", "2026-11-01T09:00:00", "Laga kraft").to_json()
        path = transfer.export_plan(self.plan, self.dir / "ut.gpkg")
        self.assertNotIn("skrivskydd", geopackage.read_meta(path))
        self.assertIn("skrivskydd", self.conn.meta, "originalet är fortfarande skyddat")

    def test_a_file_that_exists_is_never_overwritten(self):
        target = self.dir / "ut.gpkg"
        target.write_text("min egen fil")
        with self.assertRaisesRegex(transfer.TransferError, "finns redan"):
            transfer.export_plan(self.plan, target)
        self.assertEqual(target.read_text(), "min egen fil")

    def test_a_failed_export_leaves_no_half_file(self):
        target = self.dir / "ut.gpkg"

        def broken(_source, _target):  # en vanlig funktion: en mock sparar lagren den anropats med och håller filen öppen
            raise co.CheckoutError("tabellen är trasig")

        with mock.patch.object(co, "_copy_layer", broken):
            with self.assertRaisesRegex(transfer.TransferError, "trasig"):
                transfer.export_plan(self.plan, target)
        self.assertEqual([p.name for p in self.dir.glob("ut.gpkg*")], [])

    def test_a_plan_that_is_not_in_the_database_cannot_be_exported(self):
        self.conn.meta.clear()
        target = self.dir / "ut.gpkg"
        with self.assertRaisesRegex(transfer.TransferError, "finns inte"):
            transfer.export_plan(self.plan, target)
        self.assertFalse(target.exists())

    def test_file_names_are_the_plan_ids_with_the_schema_in_front_when_two_plans_share_an_id(self):
        plans = [storage.PostgisStorage("db", "a", "kv"), storage.PostgisStorage("db", "b", "kv"),
                 storage.PostgisStorage("db", "a", "annan")]
        names = [path.name for _plan, path in transfer.unique_export_paths(self.dir, plans)]
        self.assertEqual(names, ["a_kv.gpkg", "b_kv.gpkg", "annan.gpkg"])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DatabaseManagerTests(PlanCase):
    def manager(self, connections=None):
        conn = FakeConnection(plugin_schemas=["dp_a"])
        conn.plan_meta["dp_a"] = {"kv_norr": {"kommun": "Eskilstuna"}, "kv_soder": {"kommun": "Eskilstuna"}}
        conn.plan_rows["dp_a"] = [
            ["kv_norr", "Kv Norr", "1-23", "Eskilstuna", "Bostäder och park", "samråd", "detaljplan", "2026-05-02"],
            ["kv_soder", "Kv Söder", "1-24", "Eskilstuna", "Skola", "antagen", "detaljplan", None]]
        dialog = DatabaseManagerDialog(None, {"a": conn} if connections is None else connections)
        self.addCleanup(dialog.deleteLater)
        return dialog, conn

    def select(self, dialog, *plan_ids):
        dialog.table.clearSelection()
        visible = [dialog.model.item(dialog.proxy.mapToSource(dialog.proxy.index(i, 0)).row(), 0).data(ROW_ROLE).plan_id
                   for i in range(dialog.proxy.rowCount())]
        for plan_id in plan_ids:
            dialog.table.selectionModel().select(
                dialog.proxy.index(visible.index(plan_id), 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    def test_the_dialog_is_the_database_manager_with_import_and_export_buttons(self):
        dialog, _conn = self.manager()
        self.assertEqual(dialog.windowTitle(), "Databashanteraren")
        self.assertEqual((dialog.import_plan.text(), dialog.export_plans.text()), ("Importera plan…", "Exportera valda"))
        self.assertEqual([a.text() for a in dialog.export_plans.menu().actions()],
                         ["Som GeoPackage (.gpkg)…", "Som leverans, JSON (.json)…"])

    def test_import_needs_a_database_and_export_needs_selected_plans(self):
        dialog, _conn = self.manager()
        self.assertTrue(dialog.import_plan.isEnabled())
        self.assertFalse(dialog.export_plans.isEnabled())
        self.select(dialog, "kv_norr")
        self.assertTrue(dialog.export_plans.isEnabled())
        empty, _ = self.manager(connections={})
        self.assertFalse(empty.import_plan.isEnabled())

    def test_selected_plans_are_exported_to_the_chosen_folder_one_file_each(self):
        dialog, conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")
        exported = []
        with mock.patch.object(manager.QFileDialog, "getExistingDirectory", return_value=str(self.dir)), \
                mock.patch.object(manager.transfer, "export_plan", side_effect=lambda plan, path: exported.append((plan, path))):
            dialog.export_geopackage.trigger()
        self.assertEqual(sorted((plan.plan_id, path.name) for plan, path in exported),
                         [("kv_norr", "kv_norr.gpkg"), ("kv_soder", "kv_soder.gpkg")])
        self.assertTrue(all(plan.connection is conn for plan, _path in exported), "samma anslutning som i dialogen")
        self.assertIn("Exporterade 2 av 2 planer", dialog.notice.text())
        self.assertEqual(dialog.error.text(), "")

    def test_a_plan_that_cannot_be_exported_is_reported_and_the_others_are_still_exported(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")

        def export(plan, path):
            if plan.plan_id == "kv_norr":
                raise transfer.TransferError("kv_norr.gpkg finns redan.")

        with mock.patch.object(manager.QFileDialog, "getExistingDirectory", return_value=str(self.dir)), \
                mock.patch.object(manager.transfer, "export_plan", side_effect=export):
            dialog.export_geopackage.trigger()
        self.assertIn("Exporterade 1 av 2", dialog.notice.text())
        self.assertIn("kv_norr.gpkg: kv_norr.gpkg finns redan.", dialog.error.text())

    def test_cancelling_the_folder_dialog_exports_nothing(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        with mock.patch.object(manager.QFileDialog, "getExistingDirectory", return_value=""), \
                mock.patch.object(manager.transfer, "export_plan") as export:
            dialog.export_geopackage.trigger()
        export.assert_not_called()
        self.assertEqual(dialog.notice.text(), "")

    def test_selected_plans_can_be_exported_as_deliveries_with_the_json_suffix(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        exported = []
        with mock.patch.object(manager.QFileDialog, "getExistingDirectory", return_value=str(self.dir)), \
                mock.patch.object(manager.json_transfer, "export_delivery",
                                  side_effect=lambda plan, path: exported.append((plan.plan_id, path.name))):
            dialog.export_json.trigger()
        self.assertEqual(exported, [("kv_norr", "kv_norr.json")])
        self.assertIn("Exporterade 1 av 1 planer", dialog.notice.text())

    def import_with(self, dialog, conn, result):
        fake = mock.MagicMock()
        fake.exec.return_value = True
        fake.values.return_value = ImportValues(self.dir / "Ny plan.gpkg", "a", "dp_a", "ny_plan")

        def import_plan(path, connection, schema, plan_id, connection_object):
            if isinstance(result, Exception):
                raise result
            conn.plan_meta["dp_a"][plan_id] = {"kommun": "Eskilstuna"}
            return result

        with mock.patch.object(manager, "ImportPlanDialog", return_value=fake), \
                mock.patch.object(manager.transfer, "import_plan", side_effect=import_plan) as run:
            dialog.import_plan.click()
        return run

    def test_an_imported_plan_shows_up_in_the_list_selected_with_a_message(self):
        dialog, conn = self.manager()
        imported = transfer.Imported(storage.PostgisStorage("a", "dp_a", "ny_plan"), {"detaljplan": 1, "anvandning_yta": 4})
        run = self.import_with(dialog, conn, imported)
        run.assert_called_once_with(self.dir / "Ny plan.gpkg", "a", "dp_a", "ny_plan", conn)
        self.assertEqual([r.plan_id for r in dialog.selected_rows()], ["ny_plan"])
        self.assertIn("Importerade Ny plan.gpkg som ny_plan i schemat dp_a: 5 objekt.", dialog.notice.text())
        self.assertEqual(dialog.error.text(), "")

    def test_a_failed_import_shows_the_reason_and_adds_nothing(self):
        dialog, conn = self.manager()
        self.import_with(dialog, conn, storage.PostgisError("Det finns redan en plan med identifieraren ny_plan i schemat dp_a."))
        self.assertIn("Kunde inte importera Ny plan.gpkg: Det finns redan en plan", dialog.error.text())
        self.assertEqual(dialog.notice.text(), "")
        self.assertEqual([r.plan_id for r in dialog._rows], ["kv_norr", "kv_soder"])

    def import_delivery(self, dialog, conn, catalog_provider):
        dialog._catalog_provider = catalog_provider
        fake = mock.MagicMock()
        fake.exec.return_value = True
        fake.values.return_value = ImportValues(self.dir / "plan.json", "a", "dp_a", "ny_plan", JSON, "Eskilstuna", "0482", 3006)
        summary = mock.Mock(areas=3, provisions=4, warnings=("Användning: en bestämmelse hoppades över.",))
        with mock.patch.object(manager, "ImportPlanDialog", return_value=fake), \
                mock.patch.object(manager.json_transfer, "import_delivery",
                                  return_value=mock.Mock(summary=summary)) as run:
            dialog.import_plan.click()
        return run

    def test_a_delivery_is_imported_with_the_municipality_the_catalogue_and_its_warnings_shown(self):
        dialog, conn = self.manager()
        catalog = object()
        conn.plan_meta["dp_a"]["ny_plan"] = {"kommun": "Eskilstuna"}  # som när importen har lagt in planen
        run = self.import_delivery(dialog, conn, lambda: catalog)
        run.assert_called_once_with(self.dir / "plan.json", "a", "dp_a", "ny_plan", "Eskilstuna", "0482", 3006, catalog, conn)
        self.assertIn("Importerade plan.json som ny_plan i schemat dp_a: 4 bestämmelser på 3 ytor.", dialog.notice.text())
        self.assertIn("en bestämmelse hoppades över", dialog.error.text(), "det som hoppades över visas")

    def test_a_delivery_cannot_be_imported_without_the_catalogue(self):
        dialog, conn = self.manager()
        dialog._catalog_provider = None
        fake = mock.MagicMock()
        fake.exec.return_value = True
        fake.values.return_value = ImportValues(self.dir / "plan.json", "a", "dp_a", "ny_plan", JSON, "Eskilstuna", "0482", 3006)
        with mock.patch.object(manager, "ImportPlanDialog", return_value=fake):
            dialog.import_plan.click()
        self.assertIn("katalogen saknas", dialog.error.text())

    def locked_manager(self):
        dialog, conn = self.manager()
        conn.plan_meta["dp_a"]["kv_soder"]["checkout"] = other_lock().to_json()
        dialog.reload()
        return dialog, conn

    def protected_manager(self):
        dialog, conn = self.manager()
        conn.plan_meta["dp_a"]["kv_soder"]["skrivskydd"] = co.Protection(
            "anna", "ANNAS-DATOR", "2026-11-01T09:00:00", "Laga kraft").to_json()
        dialog.reload()
        return dialog, conn

    def rows_by_id(self, dialog):
        return {row.plan_id: row for row in dialog._rows}

    def test_the_overview_shows_which_plans_are_protected_and_by_whom(self):
        dialog, _conn = self.protected_manager()
        rows = self.rows_by_id(dialog)
        self.assertFalse(rows["kv_norr"].protected)
        self.assertTrue(rows["kv_soder"].protected)
        self.assertEqual(rows["kv_soder"].protection.reason, "Laga kraft")
        column = manager.COLUMN_FIELDS.index("skrivskydd")
        texts = {dialog.model.item(r, 0).text(): dialog.model.item(r, column).text() for r in range(dialog.model.rowCount())}
        self.assertEqual(texts, {"1-23": "", "1-24": "Skrivskyddad"})
        tip = dialog.model.item(1, column).toolTip() or dialog.model.item(0, column).toolTip()
        self.assertIn("Skrivskyddad av anna på ANNAS-DATOR", tip)

    def test_a_protection_row_that_cannot_be_read_still_shows_the_plan_as_protected(self):
        dialog, conn = self.manager()
        conn.plan_meta["dp_a"]["kv_norr"]["skrivskydd"] = "skräp"
        dialog.reload()
        self.assertTrue(self.rows_by_id(dialog)["kv_norr"].protected)

    def test_the_filter_shows_only_protected_or_only_editable_plans(self):
        dialog, _conn = self.protected_manager()
        shown = lambda: sorted(dialog.model.item(dialog.proxy.mapToSource(dialog.proxy.index(i, 0)).row(), 0).data(ROW_ROLE).plan_id
                               for i in range(dialog.proxy.rowCount()))
        self.assertEqual(shown(), ["kv_norr", "kv_soder"])
        dialog.filter_protect.setCurrentIndex(dialog.filter_protect.findData(manager.PROTECTED))
        self.assertEqual(shown(), ["kv_soder"])
        dialog.filter_protect.setCurrentIndex(dialog.filter_protect.findData(manager.EDITABLE))
        self.assertEqual(shown(), ["kv_norr"])

    def test_the_protect_buttons_follow_the_selection(self):
        dialog, _conn = self.protected_manager()
        buttons = (dialog.protect_plans, dialog.unprotect_plans, dialog.delete_plans, dialog.open_checkout, dialog.open_readonly)
        self.assertEqual([b.isEnabled() for b in buttons], [False, False, False, False, False], "inget valt")
        self.select(dialog, "kv_norr")
        self.assertEqual([b.isEnabled() for b in buttons], [True, False, True, True, True], "redigerbar plan")
        self.select(dialog, "kv_soder")
        self.assertEqual([b.isEnabled() for b in buttons], [False, True, False, False, True],
                         "skyddad: kan inte tas bort eller checkas ut, men öppnas skrivskyddad")
        self.select(dialog, "kv_norr", "kv_soder")
        self.assertEqual([b.isEnabled() for b in buttons], [True, True, False, False, True], "en skyddad bland de valda")

    def test_the_hint_explains_why_a_protected_plan_cannot_be_checked_out(self):
        dialog, _conn = self.protected_manager()
        self.select(dialog, "kv_soder")
        self.assertIn("skrivskyddad", dialog.hint.text())
        self.assertIn("Laga kraft", dialog.hint.text())

    def test_a_protected_plan_is_not_checked_out_from_the_dialog(self):
        dialog, _conn = self.protected_manager()
        self.select(dialog, "kv_soder")
        dialog._accept_with(True)
        self.assertFalse(dialog.checkout_requested)
        self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_selected_plans_are_protected_with_the_reason_and_the_list_is_reloaded(self):
        dialog, conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")
        with mock.patch.object(dialog, "_ask_protect", return_value="Laga kraft") as ask, \
                mock.patch.object(manager.checkout, "protect") as protect:
            dialog.protect_plans.click()
        self.assertEqual([r.plan_id for r in ask.call_args.args[0]], ["kv_norr", "kv_soder"])
        self.assertEqual([(c.args[0].plan_id, c.args[1]) for c in protect.call_args_list],
                         [("kv_norr", "Laga kraft"), ("kv_soder", "Laga kraft")])
        self.assertIn("Skrivskyddade 2 av 2 planer", dialog.notice.text())
        self.assertEqual(dialog.error.text(), "")

    def test_cancelling_the_question_protects_nothing(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        with mock.patch.object(dialog, "_ask_protect", return_value=None), \
                mock.patch.object(manager.checkout, "protect") as protect:
            dialog.protect_plans.click()
        protect.assert_not_called()

    def test_plans_that_are_already_protected_are_left_out_when_protecting(self):
        dialog, _conn = self.protected_manager()
        self.select(dialog, "kv_norr", "kv_soder")
        with mock.patch.object(dialog, "_ask_protect", return_value="") as ask, \
                mock.patch.object(manager.checkout, "protect") as protect:
            dialog.protect_plans.click()
        self.assertEqual([r.plan_id for r in ask.call_args.args[0]], ["kv_norr"])
        self.assertEqual([c.args[0].plan_id for c in protect.call_args_list], ["kv_norr"])

    def test_a_plan_that_cannot_be_protected_is_reported_and_the_others_are_still_protected(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")

        def protect(plan, reason):
            if plan.plan_id == "kv_norr":
                raise manager.checkout.CheckoutError("Planen är utcheckad och kan inte skrivskyddas.")

        with mock.patch.object(dialog, "_ask_protect", return_value=""), \
                mock.patch.object(manager.checkout, "protect", side_effect=protect):
            dialog.protect_plans.click()
        self.assertIn("Skrivskyddade 1 av 2", dialog.notice.text())
        self.assertIn("1-23: Planen är utcheckad och kan inte skrivskyddas.", dialog.error.text())

    def test_the_protection_is_lifted_only_after_confirming(self):
        dialog, conn = self.protected_manager()
        self.select(dialog, "kv_soder")
        with mock.patch.object(dialog, "_confirm_unprotect", return_value=True) as confirm, \
                mock.patch.object(manager.checkout, "unprotect") as lift:
            dialog.unprotect_plans.click()
        self.assertEqual([r.plan_id for r in confirm.call_args.args[0]], ["kv_soder"])
        lift.assert_called_once()
        self.assertEqual(lift.call_args.args[0].plan_id, "kv_soder")
        self.assertIn("Bröt skrivskyddet på 1 av 1 planer", dialog.notice.text())

    def test_declining_the_confirmation_leaves_the_protection_alone(self):
        dialog, _conn = self.protected_manager()
        self.select(dialog, "kv_soder")
        with mock.patch.object(dialog, "_confirm_unprotect", return_value=False), \
                mock.patch.object(manager.checkout, "unprotect") as lift:
            dialog.unprotect_plans.click()
        lift.assert_not_called()

    def test_protecting_and_lifting_work_against_the_database_and_show_in_the_list(self):
        conn = DeleteConnection(plugin_schemas=["dp_a"])
        conn.schema_meta["dp_a"] = {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"}
        conn.plan_meta["dp_a"] = {"kv_norr": {"kommun": "Eskilstuna"}}
        conn.plan_rows["dp_a"] = [["kv_norr", "Kv Norr", "1-23", "Eskilstuna", "Bostäder", "laga kraft", "detaljplan", None]]
        dialog = DatabaseManagerDialog(None, {"a": conn})
        self.addCleanup(dialog.deleteLater)
        self.select(dialog, "kv_norr")
        with mock.patch.object(dialog, "_ask_protect", return_value="Laga kraft"):
            dialog.protect_plans.click()
        self.assertTrue(self.rows_by_id(dialog)["kv_norr"].protected)
        self.assertIn("Laga kraft", conn.plan_meta["dp_a"]["kv_norr"]["skrivskydd"])
        self.select(dialog, "kv_norr")
        with mock.patch.object(dialog, "_confirm_unprotect", return_value=True):
            dialog.unprotect_plans.click()
        self.assertFalse(self.rows_by_id(dialog)["kv_norr"].protected)
        self.assertNotIn("skrivskydd", conn.plan_meta["dp_a"]["kv_norr"])

    def test_the_buttons_follow_the_selection_and_the_locks(self):
        dialog, _conn = self.locked_manager()
        buttons = (dialog.copy_plans, dialog.delete_plans, dialog.break_locks)
        self.assertEqual([b.isEnabled() for b in buttons], [False, False, False], "inget valt")
        self.select(dialog, "kv_norr")
        self.assertEqual([b.isEnabled() for b in buttons], [True, True, False], "ledig plan")
        self.select(dialog, "kv_soder")
        self.assertEqual([b.isEnabled() for b in buttons], [True, False, True], "utcheckad: kan inte tas bort, låset kan brytas")
        self.select(dialog, "kv_norr", "kv_soder")
        self.assertEqual([b.isEnabled() for b in buttons], [True, False, True], "en utcheckad bland de valda")

    def copy_with(self, dialog, values, copy):
        fake = mock.MagicMock()
        fake.exec.return_value = True
        fake.values.return_value = values
        with mock.patch.object(manager, "CopyPlanDialog", return_value=fake), \
                mock.patch.object(manager.transfer, "copy_plan", side_effect=copy) as run:
            dialog.copy_plans.click()
        return run

    def test_selected_plans_are_copied_one_by_one_and_the_copy_is_shown_selected(self):
        dialog, conn = self.manager()
        conn.plugin_schemas.append("dp_b")
        self.select(dialog, "kv_norr")

        def copy(plan, connection, schema, plan_id, connection_object):
            conn.plan_meta.setdefault(schema, {})[plan_id] = {"kommun": "Eskilstuna"}

        run = self.copy_with(dialog, CopyValues("a", "dp_b", ["kv_norr_ny"]), copy)
        run.assert_called_once_with(storage.PostgisStorage("a", "dp_a", "kv_norr"), "a", "dp_b", "kv_norr_ny", conn)
        self.assertEqual([r.plan_id for r in dialog.selected_rows()], ["kv_norr_ny"])
        self.assertIn("Kopierade 1 av 1 planer till schemat dp_b", dialog.notice.text())

    def test_a_plan_that_cannot_be_copied_is_reported_and_the_others_are_still_copied(self):
        dialog, conn = self.manager()
        conn.plugin_schemas.append("dp_b")
        self.select(dialog, "kv_norr", "kv_soder")

        def copy(plan, connection, schema, plan_id, connection_object):
            if plan.plan_id == "kv_norr":
                raise storage.PostgisError("Det finns redan en plan med identifieraren kv_norr i schemat dp_b.")
            conn.plan_meta.setdefault(schema, {})[plan_id] = {"kommun": "Eskilstuna"}

        self.copy_with(dialog, CopyValues("a", "dp_b", ["kv_norr", "kv_soder"]), copy)
        self.assertIn("Kopierade 1 av 2", dialog.notice.text())
        self.assertIn("kv_norr: Det finns redan en plan", dialog.error.text())

    def delete_with(self, dialog, confirm, directory="", export=None, delete=None):
        with mock.patch.object(dialog, "_confirm_delete", return_value=confirm), \
                mock.patch.object(manager.QFileDialog, "getExistingDirectory", return_value=directory), \
                mock.patch.object(manager.transfer, "export_plan", side_effect=export or (lambda plan, path: None)) as exported, \
                mock.patch.object(manager.transfer, "delete_plan", side_effect=delete or (lambda plan: None)) as deleted:
            dialog.delete_plans.click()
        return exported, deleted

    def test_cancelling_the_confirmation_removes_nothing(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        exported, deleted = self.delete_with(dialog, None)
        deleted.assert_not_called()
        exported.assert_not_called()

    def test_a_plan_is_saved_as_a_backup_before_it_is_removed(self):
        dialog, conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")
        order = []

        def delete(plan):
            order.append(("delete", plan.plan_id))
            del conn.plan_meta["dp_a"][plan.plan_id]

        exported, deleted = self.delete_with(dialog, True, str(self.dir), export=lambda plan, path: order.append(("export", path.name)),
                                             delete=delete)
        self.assertEqual(order, [("export", "kv_norr.gpkg"), ("delete", "kv_norr"), ("export", "kv_soder.gpkg"),
                                 ("delete", "kv_soder")])
        self.assertIn("Tog bort 2 av 2 planer.", dialog.notice.text())
        self.assertIn(str(self.dir), dialog.notice.text(), "var säkerhetskopiorna ligger")
        self.assertEqual(dialog._rows, [])

    def test_a_plan_whose_backup_failed_is_not_removed(self):
        dialog, conn = self.manager()
        self.select(dialog, "kv_norr", "kv_soder")

        def export(plan, path):
            if plan.plan_id == "kv_norr":
                raise transfer.TransferError("kv_norr.gpkg finns redan.")

        removed = []
        self.delete_with(dialog, True, str(self.dir), export=export, delete=lambda plan: removed.append(plan.plan_id))
        self.assertEqual(removed, ["kv_soder"], "bara planen som fick en säkerhetskopia")
        self.assertIn("Tog bort 1 av 2", dialog.notice.text())
        self.assertIn("kv_norr: kv_norr.gpkg finns redan.", dialog.error.text())

    def test_without_a_backup_the_plans_are_removed_directly(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        exported, deleted = self.delete_with(dialog, False)
        exported.assert_not_called()
        self.assertEqual([c.args[0].plan_id for c in deleted.call_args_list], ["kv_norr"])
        self.assertNotIn("Säkerhetskopiorna", dialog.notice.text())

    def test_a_backup_without_a_folder_removes_nothing(self):
        dialog, _conn = self.manager()
        self.select(dialog, "kv_norr")
        exported, deleted = self.delete_with(dialog, True, directory="")
        deleted.assert_not_called()

    def test_a_checked_out_plan_is_never_passed_to_the_removal(self):
        dialog, _conn = self.locked_manager()
        self.select(dialog, "kv_norr", "kv_soder")
        with mock.patch.object(manager.transfer, "delete_plan") as deleted, \
                mock.patch.object(dialog, "_confirm_delete") as confirm:
            dialog._delete_plans()  # även om knappen skulle trigga trots att den är avstängd
        deleted.assert_not_called()
        confirm.assert_not_called()

    def test_the_lock_of_a_checked_out_plan_can_be_broken_after_confirming(self):
        dialog, conn = self.locked_manager()
        self.select(dialog, "kv_norr", "kv_soder")
        with mock.patch.object(dialog, "_confirm_break_locks", return_value=True) as confirm, \
                mock.patch.object(manager.checkout, "break_lock") as broken:
            dialog.break_locks.click()
        self.assertEqual([r.plan_id for r in confirm.call_args.args[0]], ["kv_soder"], "bara de utcheckade planerna")
        self.assertEqual([c.args[0].plan_id for c in broken.call_args_list], ["kv_soder"])
        self.assertIn("Bröt låset på 1 av 1 planer", dialog.notice.text())

    def test_declining_the_confirmation_leaves_the_lock_alone(self):
        dialog, _conn = self.locked_manager()
        self.select(dialog, "kv_soder")
        with mock.patch.object(dialog, "_confirm_break_locks", return_value=False), \
                mock.patch.object(manager.checkout, "break_lock") as broken:
            dialog.break_locks.click()
        broken.assert_not_called()

    def test_cancelling_the_import_dialog_imports_nothing(self):
        dialog, _conn = self.manager()
        fake = mock.MagicMock()
        fake.exec.return_value = False
        with mock.patch.object(manager, "ImportPlanDialog", return_value=fake), \
                mock.patch.object(manager.transfer, "import_plan") as run:
            dialog.import_plan.click()
        run.assert_not_called()


# en minimal leverans: bara planområdet
DELIVERY = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
    "feature:typ": "detaljplan", "kommun": "Eskilstuna", "namn": "Kv Test", "beteckning": "DP 1",
    "plangeometri": [{"geometri": {"position": {"type": "Polygon",
                                                "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}}}]}}]}


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ImportPlanDialogTests(PlanCase):
    def dialog(self, **kwargs):
        conn = FakeConnection(plugin_schemas=["dp_a", "dp_b"])
        dialog = ImportPlanDialog(None, {"a": conn}, **kwargs)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def plan_file(self, name="Kv Väktaren.gpkg"):
        return geopackage.create_geopackage(self.dir / name, 3006, {"kommun": "Eskilstuna"})

    def test_nothing_can_be_imported_before_a_file_is_chosen(self):
        dialog = self.dialog()
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())

    def test_a_plan_file_gives_a_suggested_plan_id_and_shows_its_coordinate_system(self):
        dialog = self.dialog()
        dialog.file.setFilePath(str(self.plan_file()))
        self.assertEqual(dialog.plan_id.text(), "kv_vaktaren")
        self.assertIn("EPSG:3006", dialog.info.text())
        self.assertTrue(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())
        self.assertEqual(dialog.values(), ImportValues(self.dir / "Kv Väktaren.gpkg", "a", "dp_a", "kv_vaktaren"))

    def test_a_plan_id_the_user_wrote_is_not_replaced_by_a_new_suggestion(self):
        dialog = self.dialog()
        dialog.plan_id.textEdited.emit("mitt_id")
        dialog.plan_id.setText("mitt_id")
        dialog.file.setFilePath(str(self.plan_file()))
        self.assertEqual(dialog.plan_id.text(), "mitt_id")

    def test_a_file_that_is_no_plan_is_explained_and_cannot_be_imported(self):
        dialog = self.dialog()
        other = self.dir / "annat.gpkg"
        other.write_text("inte en plan")
        dialog.file.setFilePath(str(other))
        self.assertIn("ingen detaljplan", dialog.info.text())
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())

    def delivery_file(self, collection=None):
        path = self.dir / "Leverans.json"
        path.write_text(json.dumps(collection or DELIVERY), encoding="utf-8")
        return path

    def test_a_delivery_asks_for_the_municipality_and_coordinate_system_and_suggests_the_municipality(self):
        dialog = self.dialog()
        self.assertTrue(dialog.delivery_box.isHidden())
        dialog.file.setFilePath(str(self.delivery_file()))
        self.assertFalse(dialog.delivery_box.isHidden())
        self.assertEqual(dialog.plan_id.text(), "leverans")
        self.assertIn("Leverans av en detaljplan med 0 ytor", dialog.info.text())
        self.assertEqual(dialog.kommun.selected().namn, "Eskilstuna", "kommunen i filen föreslås")
        self.assertTrue(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())
        values = dialog.values()
        self.assertEqual((values.kind, values.kommun, values.kommunkod, values.epsg), (JSON, "Eskilstuna", dialog.kommun.selected().kod, 3006))

    def test_a_delivery_needs_a_municipality(self):
        dialog = self.dialog()
        dialog.file.setFilePath(str(self.delivery_file({**DELIVERY, "features": [
            {**DELIVERY["features"][0], "properties": {**DELIVERY["features"][0]["properties"], "kommun": None}}]})))
        dialog.kommun.setCurrentIndex(-1)
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())

    def test_a_json_file_that_is_no_delivery_is_explained_and_cannot_be_imported(self):
        dialog = self.dialog()
        other = self.dir / "annat.json"
        other.write_text('{"type": "Annat"}')
        dialog.file.setFilePath(str(other))
        self.assertIn("ingen leverans", dialog.info.text())
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())
        self.assertTrue(dialog.delivery_box.isHidden())

    def test_the_schema_list_holds_the_databases_schemas_and_a_new_schema_can_be_written(self):
        dialog = self.dialog(schema="dp_b")
        self.assertEqual([dialog.schema.itemText(i) for i in range(dialog.schema.count())], ["dp_a", "dp_b"])
        self.assertEqual(dialog.schema.currentText(), "dp_b")
        dialog.file.setFilePath(str(self.plan_file()))
        dialog.schema.setCurrentText("Ogiltigt Namn")
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled(), "schemanamnet är ogiltigt")
        dialog.schema.setCurrentText("nytt_schema")
        self.assertTrue(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DeliveryExportTests(CheckoutCase):
    """Exporterar den färdiga planen (som låtsasdatabasens plan) som en leverans, utan att röra projektet eller databasen."""

    def test_a_plan_is_exported_as_the_same_delivery_as_from_the_open_plan(self):
        path = json_transfer.export_delivery(self.plan, self.dir / "ut.json")
        exported = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(exported["features"][0]["properties"]["namn"], "Kv Väktaren")
        self.assertEqual(export_ngp.counts(exported), export_ngp.counts(self.export()))
        identities = lambda collection: sorted(f["properties"]["objektidentitet"] for f in collection["features"])  # noqa: E731
        self.assertEqual(identities(exported), identities(self.export()), "samma objekt, med samma identiteter")
        self.assertEqual(exported, self.export())

    def test_the_open_project_and_the_database_are_untouched(self):
        before = (sorted(self.conn.meta.items()), self.counts(), len(QgsProject.instance().mapLayers()))
        json_transfer.export_delivery(self.plan, self.dir / "ut.json")
        self.assertEqual((sorted(self.conn.meta.items()), self.counts(), len(QgsProject.instance().mapLayers())), before)

    def test_a_file_that_exists_is_never_overwritten(self):
        target = self.dir / "ut.json"
        target.write_text("min egen fil")
        with self.assertRaisesRegex(transfer.TransferError, "finns redan"):
            json_transfer.export_delivery(self.plan, target)
        self.assertEqual(target.read_text(), "min egen fil")

    def test_a_plan_that_is_not_in_the_database_cannot_be_exported(self):
        self.conn.meta.clear()
        target = self.dir / "ut.json"
        with self.assertRaisesRegex(transfer.TransferError, "finns inte"):
            json_transfer.export_delivery(self.plan, target)
        self.assertFalse(target.exists())


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DeliveryImportTests(ExportCase):
    """Importerar en leverans (den färdiga planens egen export) till låtsasdatabasen."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        self.delivery = self.dir / "leverans.json"
        self.delivery.write_text(export_ngp.dumps(self.export()), encoding="utf-8")
        self.conn = ImportConnection()

    def import_it(self, path=None, plan_id="ny_plan", catalog=None):
        return json_transfer.import_delivery(path or self.delivery, "db", "dp_new", plan_id, "Eskilstuna", "0482", 3006,
                                             catalog or self.catalog, self.conn)

    def test_a_delivery_becomes_a_new_plan_in_the_database_with_its_areas_and_provisions(self):
        result = self.import_it()
        self.assertEqual(result.summary.provisions, 4, "två användningar, en egenskapsyta och en egenskapslinje")
        self.assertEqual(result.summary.skipped, 0)
        meta = self.conn.plan_meta["dp_new"]["ny_plan"]
        self.assertEqual((meta["kommun"], meta["kommunkod"]), ("Eskilstuna", "0482"))
        self.assertEqual(self.conn.schema_meta["dp_new"]["epsg"], "3006")
        counts = result.imported.counts
        self.assertEqual((counts["detaljplan"], counts["anvandning_yta"], counts["egenskap_yta"], counts["egenskap_linje"]),
                         (1, 2, 1, 1))
        self.assertEqual(counts["bestammelse"], 4)
        self.assertEqual(result.imported.total, sum(counts.values()))
        self.assertNotIn("checkout", meta)

    def test_the_delivery_in_the_database_exports_to_the_same_content_again(self):
        """Ett varv ut och in: planens uppgifter, bestämmelsernas formuleringar och antal är desamma."""
        self.import_it()
        sql = self.conn.checkins[0]
        original = self.export()
        for provision in original["features"][1:]:
            self.assertIn(provision["properties"]["bestammelseformulering"].replace("'", "''"), sql)
        self.assertIn("Kv Väktaren", sql)

    def test_a_file_that_is_not_json_or_no_delivery_is_refused_before_the_database_is_touched(self):
        broken = self.dir / "trasig.json"
        broken.write_text("{inte json")
        other = self.dir / "annat.json"
        other.write_text('{"type": "FeatureCollection", "features": []}')
        for path, text in ((broken, "Kunde inte läsa"), (other, "ingen leverans"), (self.dir / "saknas.json", "Kunde inte läsa")):
            with self.assertRaisesRegex(transfer.TransferError, text):
                self.import_it(path)
        self.assertEqual(self.conn.sql, [])

    def test_a_plan_id_that_is_taken_is_refused_and_the_existing_plan_is_left_alone(self):
        self.conn.schema_meta["dp_new"] = {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"}
        self.conn.plan_meta["dp_new"] = {"ny_plan": {"kommun": "Annan"}}
        with self.assertRaisesRegex(storage.PostgisError, "finns redan en plan"):
            self.import_it()
        self.assertEqual(self.conn.plan_meta["dp_new"]["ny_plan"], {"kommun": "Annan"})
        self.assertEqual(self.conn.deleted, [])

    def test_provisions_missing_from_the_catalogue_are_skipped_and_reported(self):
        first = self.export()["features"][1]["properties"]["planbestammelsekatalogreferens"]
        result = self.import_it(catalog=_catalog_without(self.catalog, {first}))
        self.assertGreaterEqual(result.summary.skipped, 1)
        self.assertEqual(result.summary.skipped + result.summary.provisions, 4)
        self.assertTrue(any("finns inte i katalogen" in warning for warning in result.summary.warnings))

    def test_the_temporary_files_are_removed_and_the_open_project_is_untouched(self):
        layers = len(QgsProject.instance().mapLayers())
        self.import_it()
        self.assertEqual(len(QgsProject.instance().mapLayers()), layers)


class DeleteConnection(ImportConnection):
    """Låtsasdatabas som också tar emot borttagningen: kastar fel om planen är utcheckad, annars tar den bort planens uppgifter."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.removals = []

    def executeSql(self, sql):
        if sql.startswith("DELETE FROM") and "'skrivskydd'" in sql:  # bryt skrivskyddet
            self.sql.append(sql)
            schema = re.search(r'DELETE FROM "(\w+)"', sql).group(1)
            plan_id = re.search(r'"plan" = \'([^\']*)\'', sql).group(1)
            self.plan_meta[schema][plan_id].pop("skrivskydd", None)
            return []
        if sql.startswith("DO $dp$ BEGIN LOCK TABLE") and "kan inte skrivskyddas" in sql:  # skrivskydda planen
            self.sql.append(sql)
            schema = re.search(r'LOCK TABLE "(\w+)"', sql).group(1)
            plan_id, value = re.search(r"VALUES \('([^']*)', 'skrivskydd', '(.*)'\); END IF", sql).groups()
            meta = self.plan_meta[schema][plan_id]
            if "checkout" in meta:
                raise RuntimeError("Planen är utcheckad och kan inte skrivskyddas. Checka in den eller bryt låset först.")
            meta.setdefault("skrivskydd", value.replace("''", "'"))
            return []
        if sql.startswith("DO $dp$ BEGIN LOCK TABLE") and "RAISE EXCEPTION" in sql:
            self.sql.append(sql)
            schema = re.search(r'LOCK TABLE "(\w+)"', sql).group(1)
            plan_id = re.search(r'"plan" = \'([^\']*)\'', sql).group(1)
            if "checkout" in self.plan_meta[schema][plan_id]:
                raise RuntimeError(transfer.LOCKED_MESSAGE)
            if "skrivskydd" in self.plan_meta[schema][plan_id]:
                raise RuntimeError(transfer.PROTECTED_MESSAGE)
            self.removals.append(sql)
            del self.plan_meta[schema][plan_id]
            return []
        return super().executeSql(sql)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CopyTests(CheckoutCase):
    """Kopierar den färdiga planen (databasens plan) till en annan databas."""

    def setUp(self):
        super().setUp()
        self.target = ImportConnection()

    def copy_it(self, plan_id="kopia", schema="dp_kopia"):
        return transfer.copy_plan(self.plan, "db2", schema, plan_id, self.target)

    def test_a_plan_is_copied_with_its_details_and_every_row_to_another_database(self):
        result = self.copy_it()
        self.assertEqual(result.counts, self.counts())
        self.assertEqual(result.plan, storage.PostgisStorage("db2", "dp_kopia", "kopia"))
        meta = self.target.plan_meta["dp_kopia"]["kopia"]
        self.assertEqual(meta["kommun"], geopackage.read_meta(self.gpkg)["kommun"])
        self.assertEqual(self.target.schema_meta["dp_kopia"]["epsg"], geopackage.read_meta(self.gpkg)["epsg"])
        self.assertIn("'kopia'", self.target.checkins[0], "raderna får den nya planens id")

    def test_a_protected_plan_can_be_copied_and_the_copy_is_not_protected(self):
        protection = co.Protection("anna", "ANNAS-DATOR", "2026-11-01T09:00:00", "Laga kraft")
        self.conn.meta["skrivskydd"] = protection.to_json()
        self.copy_it()
        self.assertNotIn("skrivskydd", self.target.plan_meta["dp_kopia"]["kopia"], "kopian är en ny plan som får ändras")
        self.assertEqual(co.read_protection(self.plan), protection, "originalet är fortfarande skyddat")

    def test_the_source_is_not_changed_and_a_lock_is_not_copied(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        sql_before = len(self.conn.sql)
        self.copy_it()
        self.assertEqual(co.read_lock(self.plan), other_lock(), "den andras lås är orört")
        self.assertNotIn("checkout", self.target.plan_meta["dp_kopia"]["kopia"])
        self.assertFalse([q for q in self.conn.sql[sql_before:] if q.startswith(("DELETE", "INSERT", "DO"))],
                         "inget skrivs till källan")

    def test_a_plan_id_that_is_taken_is_refused_and_nothing_is_overwritten(self):
        self.target.schema_meta["dp_kopia"] = {"schema_version": str(model.SCHEMA_VERSION),
                                               "epsg": geopackage.read_meta(self.gpkg)["epsg"]}
        self.target.plan_meta["dp_kopia"] = {"kopia": {"kommun": "Annan"}}
        with self.assertRaisesRegex(storage.PostgisError, "finns redan en plan"):
            self.copy_it()
        self.assertEqual(self.target.plan_meta["dp_kopia"]["kopia"], {"kommun": "Annan"})
        self.assertEqual(self.target.deleted, [])

    def test_a_plan_that_is_not_in_the_database_cannot_be_copied(self):
        self.conn.meta.clear()
        with self.assertRaisesRegex(transfer.TransferError, "finns inte"):
            self.copy_it()
        self.assertEqual(self.target.sql, [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DeleteTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.conn = DeleteConnection()
        self.conn.schema_meta["dp_a"] = {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"}
        self.conn.plan_meta["dp_a"] = {"kv_norr": {"kommun": "Eskilstuna"}, "kv_soder": {"kommun": "Eskilstuna"}}
        self.plan = storage.PostgisStorage("db", "dp_a", "kv_norr", self.conn)

    def test_a_plan_is_removed_from_every_table_in_one_transaction_and_other_plans_are_untouched(self):
        transfer.delete_plan(self.plan)
        self.assertNotIn("kv_norr", self.conn.plan_meta["dp_a"])
        self.assertIn("kv_soder", self.conn.plan_meta["dp_a"])
        sql, = self.conn.removals
        self.assertIn('LOCK TABLE "dp_a"."dp_meta" IN EXCLUSIVE MODE', sql)
        for layer_def in model.LAYERS:
            self.assertIn(f'DELETE FROM "dp_a"."{layer_def.name}" WHERE "plan" = \'kv_norr\'', sql)
        self.assertIn('DELETE FROM "dp_a"."dp_meta" WHERE "plan" = \'kv_norr\'', sql)
        self.assertNotIn("kv_soder", sql)

    def test_a_checked_out_plan_is_never_removed_not_even_the_users_own(self):
        lock = co.new_lock()  # den här användarens egen utcheckning
        for held in (other_lock(), lock):
            self.conn.plan_meta["dp_a"]["kv_norr"]["checkout"] = held.to_json()
            with self.assertRaisesRegex(transfer.TransferError, "utcheckad av .*bryt låset"):
                transfer.delete_plan(self.plan)
        self.assertIn("kv_norr", self.conn.plan_meta["dp_a"])
        self.assertEqual(self.conn.removals, [])

    def test_a_lock_taken_just_before_the_removal_stops_it(self):
        """Någon hinner checka ut planen mellan kontrollen och borttagningen: databasen vägrar."""
        self.conn.plan_meta["dp_a"]["kv_norr"]["checkout"] = other_lock().to_json()
        with mock.patch.object(co, "read_lock", return_value=None):
            with self.assertRaisesRegex(transfer.TransferError, "utcheckad och kan inte tas bort"):
                transfer.delete_plan(self.plan)
        self.assertIn("kv_norr", self.conn.plan_meta["dp_a"])

    def test_a_protected_plan_is_never_removed_until_the_protection_is_lifted(self):
        co.protect(self.plan, "Laga kraft")
        with self.assertRaisesRegex(transfer.TransferError, "skrivskyddad av .*Laga kraft.*Bryt skrivskyddet"):
            transfer.delete_plan(self.plan)
        self.assertIn("kv_norr", self.conn.plan_meta["dp_a"])
        self.assertEqual(self.conn.removals, [])
        co.unprotect(self.plan)
        transfer.delete_plan(self.plan)
        self.assertNotIn("kv_norr", self.conn.plan_meta["dp_a"])

    def test_a_protection_set_just_before_the_removal_stops_it(self):
        """Någon hinner skydda planen mellan kontrollen och borttagningen: databasen vägrar."""
        self.conn.plan_meta["dp_a"]["kv_norr"]["skrivskydd"] = co.Protection("anna", "ANNAS-DATOR", "2026-11-01T09:00:00").to_json()
        with mock.patch.object(co, "read_protection", return_value=None):
            with self.assertRaisesRegex(transfer.TransferError, "skrivskyddad och kan inte tas bort"):
                transfer.delete_plan(self.plan)
        self.assertIn("kv_norr", self.conn.plan_meta["dp_a"])

    def test_the_removal_sql_checks_the_protection_while_the_meta_table_is_locked(self):
        sql = transfer.delete_sql("dp_a", "kv_norr")
        self.assertLess(sql.index("LOCK TABLE"), sql.index("'skrivskydd'"))
        self.assertLess(sql.index("'skrivskydd'"), sql.index('DELETE FROM "dp_a"."'))

    def test_a_plan_that_does_not_exist_cannot_be_removed(self):
        with self.assertRaisesRegex(transfer.TransferError, "finns inte"):
            transfer.delete_plan(storage.PostgisStorage("db", "dp_a", "spöke", self.conn))
        self.assertEqual(self.conn.removals, [])

    def test_a_plan_that_is_still_there_after_the_removal_is_reported(self):
        with mock.patch.object(storage, "plan_exists", return_value=True):
            with self.assertRaisesRegex(transfer.TransferError, "finns kvar"):
                transfer.delete_plan(self.plan)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CopyPlanDialogTests(PlanCase):
    def rows(self, *plan_ids):
        return [PlanRow("a", "dp_a", plan_id, beteckning=plan_id.upper()) for plan_id in plan_ids]

    def dialog(self, rows):
        conn = FakeConnection(plugin_schemas=["dp_a", "dp_b"])
        dialog = CopyPlanDialog(None, {"a": conn}, rows)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def ok(self, dialog):
        return dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()

    def test_a_copy_in_the_same_place_suggests_another_plan_id_and_a_copy_elsewhere_keeps_the_id(self):
        dialog = self.dialog(self.rows("kv_norr"))
        self.assertEqual(dialog.plan_id.text(), "kv_norr_kopia")
        self.assertTrue(self.ok(dialog))
        dialog.target.schema.setCurrentText("dp_b")
        self.assertEqual(dialog.plan_id.text(), "kv_norr")
        self.assertEqual(dialog.values(), CopyValues("a", "dp_b", ["kv_norr"]))

    def test_a_plan_cannot_be_copied_onto_itself(self):
        dialog = self.dialog(self.rows("kv_norr"))
        dialog.plan_id.textEdited.emit("kv_norr")
        dialog.plan_id.setText("kv_norr")
        self.assertFalse(self.ok(dialog))
        self.assertIn("finns redan där", dialog.info.text())

    def test_an_invalid_plan_id_or_schema_cannot_be_used(self):
        dialog = self.dialog(self.rows("kv_norr"))
        dialog.plan_id.setText("Ogiltigt Id")
        self.assertFalse(self.ok(dialog))
        dialog.plan_id.setText("giltigt_id")
        self.assertTrue(self.ok(dialog))
        dialog.target.schema.setCurrentText("Ogiltigt Schema")
        self.assertFalse(self.ok(dialog))

    def test_several_plans_keep_their_plan_ids_and_need_another_schema(self):
        dialog = self.dialog(self.rows("kv_norr", "kv_soder"))
        self.assertEqual(dialog.windowTitle(), "Kopiera 2 planer")
        self.assertFalse(self.ok(dialog), "samma schema: planerna skulle krocka med sig själva")
        self.assertIn("behåller sina plan-id", dialog.info.text())
        dialog.target.schema.setCurrentText("dp_b")
        self.assertTrue(self.ok(dialog))
        self.assertEqual(dialog.values().plan_ids, ["kv_norr", "kv_soder"])


def _catalog_without(catalog, references):
    """Katalogen utan poster med de angivna referenserna (för att prova att en bestämmelse hoppas över)."""
    class Without:
        def get(self, identifier):
            return None if identifier in references else catalog.get(identifier)

    return Without()


if __name__ == "__main__":
    unittest.main()
