"""Planmosaiken: alla planer i ett schema som en skrivskyddad vy (kräver QGIS; databasen och PostGIS-lagren är låtsas,
se test_postgis)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PlanCase  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsDataSourceUri, QgsProject, QgsRectangle
    from qgis.PyQt.QtCore import Qt
    from test_postgis import FakeConnection, gpkg_backed
    from test_toolbar import GuiCase

    import rita_detaljplan
    from rita_detaljplan.core import geopackage, mosaic, storage, symbology
    from rita_detaljplan.core.project import TABLE_PROPERTY, find_layer, find_plan_group, load_plan, plan_groups
    from rita_detaljplan.gui.mosaic_dialog import MosaicDialog


class ConditionTests(unittest.TestCase):
    def test_statuses_become_an_in_list_and_are_quoted(self):
        self.assertEqual(mosaic.status_condition(["laga kraft", "antagen"]), "(\"status\" IN ('laga kraft', 'antagen'))")
        self.assertIn("''", mosaic.status_condition(["it's"]))

    def test_plans_without_a_status_are_included_when_asked_for(self):
        condition = mosaic.status_condition(["laga kraft", mosaic.NO_STATUS])
        self.assertIn("\"status\" IN ('laga kraft')", condition)
        self.assertIn("\"status\" IS NULL", condition)
        self.assertEqual(mosaic.status_condition([mosaic.NO_STATUS]), "(\"status\" IS NULL OR \"status\" = '')")

    def test_no_status_at_all_is_refused(self):
        with self.assertRaises(ValueError):
            mosaic.status_condition([])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LoadMosaicTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.backing = self.dir / "backing.gpkg"
        geopackage.create_geopackage(self.backing, 3006, {"kommun": "Eskilstuna", "kommunkod": "0484"})
        self.conn = FakeConnection()
        meta = geopackage.read_meta(self.backing)
        self.conn.schema_meta["dp_test"] = {"schema_version": meta["schema_version"], "epsg": meta["epsg"]}
        self.conn.plan_meta["dp_test"] = {"dp_1": {k: v for k, v in meta.items()
                                                    if k not in ("schema_version", "epsg")}}
        self.uris = []
        opener = gpkg_backed(self.backing)

        def open_layer(storage_self, uri, alias):
            self.uris.append(uri)
            return opener(storage_self, uri, alias)

        patcher = mock.patch.object(storage.PostgisStorage, "_open", open_layer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def load(self, project=None, statuses=("laga kraft",)):
        project = project if project is not None else QgsProject()
        return project, mosaic.load_mosaic(project, "db", "dp_test", statuses, self.conn)

    def test_the_mosaic_is_one_group_with_the_layers_of_the_plan_areas_and_their_content(self):
        project, opened = self.load()
        self.assertEqual(set(opened.layers), {d.name for d in mosaic.MOSAIC_LAYERS} | {mosaic.OVERVIEW_USE})
        self.assertEqual([c.layer().name() for c in opened.group.children()],
                         [d.alias for d in mosaic.MOSAIC_LAYERS] + ["Användning (yta) (översikt)"])
        self.assertEqual([g.name() for g in mosaic.mosaic_groups(project)], [opened.group.name()])
        self.assertIn("dp_test", opened.group.name())
        self.assertIn("laga kraft", opened.group.name())

    def test_the_layers_read_every_plan_with_a_chosen_status_not_one_plan(self):
        self.load(statuses=("laga kraft", "antagen"))
        areas = next(QgsDataSourceUri(u) for u in self.uris if QgsDataSourceUri(u).table() == "anvandning_yta")
        self.assertIn("\"plan\" IN (SELECT \"plan\" FROM \"dp_test\".\"detaljplan\" WHERE (\"status\" IN ('laga kraft', 'antagen')))",
                      areas.sql())
        self.assertNotIn("= 'dp_1'", areas.sql())
        plan_area = next(QgsDataSourceUri(u) for u in self.uris if QgsDataSourceUri(u).table() == "detaljplan")
        self.assertEqual(plan_area.sql(), "(\"status\" IN ('laga kraft', 'antagen'))")

    def test_the_layers_are_read_only_and_get_the_look_of_a_plan(self):
        _project, opened = self.load()
        for layer in opened.layers.values():
            self.assertTrue(layer.readOnly())
        self.assertEqual(opened.layers["anvandning_yta"].renderer().referenceScale(), 1000)
        self.assertIsNotNone(opened.layers["detaljplan"].renderer())

    def test_no_labels_are_drawn_in_the_mosaic(self):
        _project, opened = self.load()
        for layer in opened.layers.values():
            self.assertFalse(layer.labelsEnabled(), layer.name())

    def test_what_lacks_provisions_is_drawn_like_the_rest_not_red_or_hatched(self):
        _project, opened = self.load()
        for table in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            renderer = opened.layers[table].renderer()
            categories = {c.value(): c for c in renderer.categories()}
            missing, others = categories[symbology.UNASSIGNED], categories[""]
            self.assertEqual([l.layerType() for l in missing.symbol().symbolLayers()],
                             [l.layerType() for l in others.symbol().symbolLayers()], table)
            self.assertEqual(missing.symbol().color().name(), others.symbol().color().name(), table)
            self.assertEqual(missing.label(), others.label(), table)

    def test_in_a_plan_what_lacks_provisions_is_still_marked(self):
        project = QgsProject()
        layers = load_plan(storage.PostgisStorage("db", "dp_test", "dp_1", self.conn), project)
        renderer = layers["anvandning_yta"].renderer()
        missing = {c.value(): c for c in renderer.categories()}[symbology.UNASSIGNED]
        self.assertIn("LinePatternFill", [l.layerType() for l in missing.symbol().symbolLayers()])

    def test_the_plan_area_boundary_is_solid_in_the_mosaic_but_dashed_in_a_plan_and_otherwise_the_same(self):
        _project, opened = self.load()
        lines = [l for l in opened.layers["detaljplan"].renderer().symbol().symbolLayers() if l.layerType() == "SimpleLine"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].penStyle(), Qt.PenStyle.SolidLine)
        self.assertFalse(lines[0].useCustomDashPattern())
        project = QgsProject()
        layers = load_plan(storage.PostgisStorage("db", "dp_test", "dp_1", self.conn), project)
        plan_lines = [l for l in layers["detaljplan"].renderer().symbol().symbolLayers() if l.layerType() == "SimpleLine"]
        self.assertTrue(plan_lines[0].useCustomDashPattern() or plan_lines[0].penStyle() != Qt.PenStyle.SolidLine)
        self.assertEqual(lines[0].width(), plan_lines[0].width(), "samma bredd som planens egen gräns")
        self.assertEqual(lines[0].color().name(), plan_lines[0].color().name())

    def test_the_plan_area_boundary_scales_with_the_map_like_every_other_layer(self):
        _project, opened = self.load()
        scales = {name: layer.renderer().referenceScale() for name, layer in opened.layers.items()}
        self.assertGreater(scales["detaljplan"], 0)
        self.assertEqual(set(scales.values()), {scales["detaljplan"]}, f"samma referensskala i alla lager: {scales}")

    def line_of(self, layer, category_index=0):
        """Kantlinjens egenskaper (som vanliga värden: objekten hör till kopior som tas bort när funktionen är klar) och
        uttrycket i användningslagrets första kategori: (penna, eget streckmönster, bredd, uttryck)."""
        categories = layer.renderer().categories()  # mellanleden binds till variabler: temporära objekt kan krascha
        symbol = categories[category_index].symbol()
        generators = [l for l in symbol.symbolLayers() if l.layerType() == "GeometryGenerator"]
        self.assertEqual(len(generators), 1, "ett kantlinjeskikt per kategori, inget skaluttryck")
        sub = generators[0].subSymbol()
        line = [l for l in sub.symbolLayers() if l.layerType() == "SimpleLine"][0]
        return line.penStyle(), line.useCustomDashPattern(), line.width(), generators[0].geometryExpression()

    def plain_line_of(self, layer, category_index=0):
        """Kantlinjen när den är en vanlig linje i fyllningssymbolen (inget kantlinjeskikt med uttryck): (penna, eget
        streckmönster, bredd, antal geometrigeneratorer)."""
        categories = layer.renderer().categories()
        symbol = categories[category_index].symbol()
        types = [l.layerType() for l in symbol.symbolLayers()]
        line = [l for l in symbol.symbolLayers() if l.layerType() == "SimpleLine"][0]
        return line.penStyle(), line.useCustomDashPattern(), line.width(), types.count("GeometryGenerator")

    def test_the_use_areas_are_two_layers_dashed_boundary_when_zoomed_in_and_solid_when_zoomed_out(self):
        _project, opened = self.load()
        detail, overview = opened.layers["anvandning_yta"], opened.layers[mosaic.OVERVIEW_USE]
        for layer in (detail, overview):
            self.assertTrue(layer.hasScaleBasedVisibility())
            self.assertTrue(layer.readOnly())
        # exakt ett av dem ritas i varje skala (QGIS räknar minimiskalan som exklusiv och maxskalan som inklusiv)
        for scale in (100, 500, 1999, 2000, 2001, 6000, 50_000, 199_999, 200_000, 250_000, 5_000_000):
            self.assertLessEqual(int(detail.isInScaleRange(scale)) + int(overview.isInScaleRange(scale)), 1, scale)
        for scale in (100, 1999):
            self.assertTrue(detail.isInScaleRange(scale), scale)
            self.assertFalse(overview.isInScaleRange(scale), scale)
        for scale in (2001, 6000, 50_000, 199_999):
            self.assertFalse(detail.isInScaleRange(scale), scale)
            self.assertTrue(overview.isInScaleRange(scale), scale)
        self.assertFalse(detail.isInScaleRange(250_000) or overview.isInScaleRange(250_000), "längre ut ritas inget")
        dashed_pen, dashed_custom, _width, hierarchy = self.line_of(detail)
        solid_pen, solid_custom, _width, generators = self.plain_line_of(overview)
        self.assertTrue(dashed_custom or dashed_pen != Qt.PenStyle.SolidLine, "streckad inzoomat")
        self.assertEqual(solid_pen, Qt.PenStyle.SolidLine)
        self.assertFalse(solid_custom)
        self.assertEqual(generators, 0, "översikten har ingen beräknad kant, bara fyllningens egen kantlinje")
        self.assertIn("overlay_nearest", hierarchy, "inzoomat döljs kanter som redan ritas, som i en plan")
        self.assertNotIn("@map_scale", hierarchy, "inget skaluttryck: det gjorde ritningen långsammare")

    def test_both_use_layers_have_the_same_fill_and_categories(self):
        _project, opened = self.load()
        detail = opened.layers["anvandning_yta"].renderer().categories()
        overview = opened.layers[mosaic.OVERVIEW_USE].renderer().categories()
        self.assertEqual([(c.value(), c.label()) for c in detail], [(c.value(), c.label()) for c in overview])
        for a, b in zip(detail, overview):
            fill_a = a.symbol().symbolLayer(0).color().name()
            fill_b = b.symbol().symbolLayer(0).color().name()
            self.assertEqual(fill_a, fill_b, a.label())
        self.assertEqual(opened.layers[mosaic.OVERVIEW_USE].blendMode(), opened.layers["anvandning_yta"].blendMode())

    def test_the_solid_use_boundary_is_narrower_than_the_plan_area_boundary(self):
        _project, opened = self.load()
        _pen, _custom, use_width, _generators = self.plain_line_of(opened.layers[mosaic.OVERVIEW_USE])
        plan_symbol = opened.layers["detaljplan"].renderer().symbol()
        plan_line = [l for l in plan_symbol.symbolLayers() if l.layerType() == "SimpleLine"][0]
        self.assertLess(use_width, plan_line.width())

    def fill_backing_with_a_plan_of_two_uses(self):
        """Ett planområde (0-100 m) med två användningsytor sida vid sida, i den GeoPackage som lagren läses ur."""
        from qgis.core import QgsExpressionContext, QgsExpressionContextUtils, QgsGeometry, QgsVectorLayerUtils
        setup_project = QgsProject()  # hålls kvar: ett temporärt projekt tar bort lagren
        loaded = load_plan(self.backing, setup_project)

        def add(table, x0, x1, **attributes):
            layer = loaded[table]
            layer.startEditing()
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            wkt = f"MultiPolygon((({x0} 0, {x1} 0, {x1} 100, {x0} 100, {x0} 0)))"
            indexes = {layer.fields().indexOf(k): v for k, v in attributes.items()}
            layer.addFeature(QgsVectorLayerUtils.createFeature(layer, QgsGeometry.fromWkt(wkt), indexes, context))
            self.assertTrue(layer.commitChanges(), layer.commitErrors())

        add("detaljplan", 0, 100, status="laga kraft")
        add("anvandning_yta", 0, 50, bestammelser=1, farg="Gul")
        add("anvandning_yta", 50, 100, bestammelser=1, farg="Brun")

    def render_mosaic(self, opened, scale):
        """Ritar mosaiken centrerad på mitten av planen i skalan 1:``scale`` (med kartans uttryckskontext, som i QGIS)."""
        from qgis.core import (QgsCoordinateReferenceSystem, QgsExpressionContext, QgsExpressionContextUtils,
                               QgsMapRendererParallelJob, QgsMapSettings)
        from qgis.PyQt.QtCore import QEventLoop, QSize, QTimer
        from qgis.PyQt.QtGui import QColor
        width, height, dpi = 700, 420, 96
        extent_w = scale * (width / dpi * 0.0254)
        extent_h = extent_w * height / width
        settings = QgsMapSettings()
        settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3006"))
        settings.setLayers(list(opened.layers.values()))
        settings.setExtent(QgsRectangle(50 - extent_w / 2, 50 - extent_h / 2, 50 + extent_w / 2, 50 + extent_h / 2))
        settings.setOutputSize(QSize(width, height))
        settings.setOutputDpi(dpi)
        settings.setBackgroundColor(QColor("white"))
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.mapSettingsScope(settings))
        settings.setExpressionContext(context)
        job = QgsMapRendererParallelJob(settings)
        # vänta med en händelseslinga (waitForFinished blockerar och ger dödläge när uttryck hämtar från andra lager)
        loop = QEventLoop()
        job.finished.connect(loop.quit)
        QTimer.singleShot(60_000, loop.quit)
        job.start()
        loop.exec()
        self.assertFalse(job.isActive(), "renderingen blev inte klar")
        return job.renderedImage()

    @staticmethod
    def boundary_column(image):
        """Kolumnen i mitten av bilden (mellan de två användningsytorna) med de värden som finns längs den."""
        columns = {x: [image.pixelColor(x, y).red() for y in range(195, 225)] for x in range(344, 357)}
        x = min(columns, key=lambda c: sum(columns[c]))  # den mörkaste kolumnen är linjen
        return x, columns[x]

    def test_the_use_boundary_is_solid_when_zoomed_out_past_1_to_2000_and_dashed_closer(self):
        self.fill_backing_with_a_plan_of_two_uses()
        _project, opened = self.load(QgsProject.instance())  # uttrycken slår upp lager i det globala projektet
        _x, near = self.boundary_column(self.render_mosaic(opened, 1500))
        _x, far = self.boundary_column(self.render_mosaic(opened, 6000))
        self.assertGreater(max(near) - min(near), 100, f"streckad närmare än 1:2000: {near}")
        self.assertLessEqual(max(far) - min(far), 12, f"heldragen längre ut än 1:2000: {far}")
        self.assertLess(max(far), 218, f"linjen syns (mörkare än ytan intill): {far}")

    def test_in_a_plan_the_use_boundary_has_no_scale_dependence(self):
        project = QgsProject()
        layers = load_plan(storage.PostgisStorage("db", "dp_test", "dp_1", self.conn), project)
        for category in layers["anvandning_yta"].renderer().categories():
            generators = [l for l in category.symbol().symbolLayers() if l.layerType() == "GeometryGenerator"]
            self.assertEqual(len(generators), 1, category.label())

    def test_details_are_drawn_from_a_scale_but_the_plan_areas_always(self):
        _project, opened = self.load()
        overview = opened.layers[mosaic.OVERVIEW_USE]
        self.assertTrue(overview.hasScaleBasedVisibility())
        self.assertEqual(overview.minimumScale(), mosaic.DETAIL_SCALE)
        self.assertFalse(opened.layers["detaljplan"].hasScaleBasedVisibility())

    def test_property_points_are_not_loaded_because_they_draw_nothing_in_the_mosaic(self):
        _project, opened = self.load()
        self.assertNotIn("egenskap_punkt", opened.layers)
        tables = {QgsDataSourceUri(uri).table() for uri in self.uris}
        self.assertNotIn("egenskap_punkt", tables, "ingen fråga mot en tabell som inte ritas")
        self.assertEqual(tables, {"detaljplan", "anvandning_yta", "egenskap_yta", "egenskap_linje"})

    def test_property_areas_and_lines_are_drawn_only_from_1_to_2000(self):
        _project, opened = self.load()
        self.assertEqual(mosaic.PROPERTY_SCALE, 2000)
        for table in ("egenskap_yta", "egenskap_linje"):
            layer = opened.layers[table]
            self.assertTrue(layer.hasScaleBasedVisibility(), table)
            self.assertEqual(layer.minimumScale(), 2000, table)
            # QGIS räknar minimiskalan som exklusiv, som i lagerdialogen: 1:2000 är gränsen, 1:1999 ritas
            self.assertTrue(layer.isInScaleRange(1999) and layer.isInScaleRange(500), table)
            self.assertFalse(layer.isInScaleRange(2001) or layer.isInScaleRange(5000), table)
        use = opened.layers[mosaic.OVERVIEW_USE]
        self.assertTrue(use.isInScaleRange(50_000), "användningsytorna ritas i en mycket mindre skala")
        self.assertEqual(use.minimumScale(), mosaic.DETAIL_SCALE)

    def test_the_plugins_tools_never_see_the_mosaic_as_a_plan(self):
        project, opened = self.load()
        self.assertEqual(plan_groups(project), [])
        self.assertIsNone(find_plan_group(project))
        self.assertIsNone(find_layer(project, "anvandning_yta"))
        for layer in opened.layers.values():
            self.assertIsNone(layer.customProperty(TABLE_PROPERTY))

    def test_a_loaded_plan_stays_the_active_plan_next_to_a_mosaic(self):
        project = QgsProject()
        layers = load_plan(storage.PostgisStorage("db", "dp_test", "dp_1", self.conn), project)
        self.load(project)
        self.assertIs(find_layer(project, "anvandning_yta"), layers["anvandning_yta"])
        self.assertEqual(len(plan_groups(project)), 1)

    def test_opening_the_mosaic_again_replaces_it(self):
        project, first = self.load()
        before = len(project.mapLayers())
        _project, second = self.load(project, statuses=("antagen",))
        self.assertEqual(len(project.mapLayers()), before, "inga lager blir kvar från den första mosaiken")
        self.assertEqual(len(mosaic.mosaic_groups(project)), 1)
        self.assertIn("antagen", mosaic.mosaic_groups(project)[0].name())
        self.assertIsNot(first.group, second.group)

    def test_the_project_follows_the_coordinate_system_of_the_schema(self):
        project, _opened = self.load()
        self.assertEqual(project.crs().authid(), "EPSG:3006")

    def test_a_schema_with_an_older_version_is_refused_with_advice(self):
        self.conn.schema_meta["dp_test"]["schema_version"] = "8"
        with self.assertRaisesRegex(ValueError, "Öppna en plan i schemat först"):
            self.load()

    def test_something_that_is_not_a_plugin_schema_is_refused(self):
        with self.assertRaisesRegex(ValueError, "inte ett schema"):
            mosaic.load_mosaic(QgsProject(), "db", "public", ["laga kraft"], self.conn)

    def test_no_chosen_status_is_refused_before_anything_is_read(self):
        with self.assertRaises(ValueError):
            self.load(statuses=())
        self.assertEqual(self.uris, [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class MosaicDialogTests(PlanCase):
    def dialog(self, counts=None):
        conn = FakeConnection(plugin_schemas=["dp_a", "dp_b"])
        conn.status_counts["dp_a"] = counts or {"laga kraft": 12, "antagen": 2, "upphävd": 5, "påbörjad": 3, "": 1}
        conn.status_counts["dp_b"] = {"laga kraft": 4}
        return MosaicDialog(None, {"db": conn})

    def test_the_statuses_in_the_schema_are_listed_in_the_order_of_a_plans_life_with_their_counts(self):
        dialog = self.dialog()
        labels = [check.text() for check in dialog._checks.values()]
        self.assertEqual(labels, ["påbörjad (3)", "antagen (2)", "laga kraft (12)", "upphävd (5)", "utan status (1)"])

    def test_plans_in_force_are_chosen_from_the_start(self):
        dialog = self.dialog()
        self.assertEqual(dialog.statuses(), ["antagen", "laga kraft"])
        self.assertEqual(dialog.selection(), ("db", "dp_a", ["antagen", "laga kraft"]))
        self.assertEqual(dialog.plan_count(), 14)
        self.assertIn("14 planer", dialog.summary.text())
        self.assertTrue(dialog.open_button.isEnabled())

    def test_nothing_chosen_disables_the_button(self):
        dialog = self.dialog()
        for check in dialog._checks.values():
            check.setChecked(False)
        self.assertFalse(dialog.open_button.isEnabled())
        self.assertIsNone(dialog.selection())

    def test_changing_schema_lists_that_schemas_statuses(self):
        dialog = self.dialog()
        dialog.schema.setCurrentIndex(dialog.schema.findData("dp_b"))
        self.assertEqual(list(dialog._checks), ["laga kraft"])
        self.assertEqual(dialog.selection(), ("db", "dp_b", ["laga kraft"]))

    def test_the_connection_and_schema_chosen_before_are_preselected(self):
        conn_a, conn_b = FakeConnection(plugin_schemas=["dp_a"]), FakeConnection(plugin_schemas=["dp_x", "dp_y"])
        conn_b.status_counts["dp_y"] = {"laga kraft": 7}
        dialog = MosaicDialog(None, {"a": conn_a, "b": conn_b}, connection="b", schema="dp_y")
        self.assertEqual(dialog.selection(), ("b", "dp_y", ["laga kraft"]))

    def test_an_unknown_preselection_is_ignored(self):
        dialog = MosaicDialog(None, {"db": FakeConnection(plugin_schemas=["dp_a"])}, connection="finns_inte",
                              schema="finns_inte")
        self.assertEqual(dialog.connection.currentData(), "db")
        self.assertEqual(dialog.schema.currentData(), "dp_a")

    def test_the_intro_keeps_its_comma_and_writes_the_scale_with_a_space(self):
        dialog = self.dialog()
        text = dialog.intro.text()
        self.assertIn("tillsammans, som en enda", text)
        self.assertIn("1:200 000", text)
        self.assertIn("1:2 000", text)

    def test_a_schema_that_cannot_be_read_gives_a_message_that_goes_away_when_another_is_chosen(self):
        conn = FakeConnection(plugin_schemas=["dp_a", "dp_b"], fail_on='"dp_a"."detaljplan"')
        conn.status_counts["dp_b"] = {"laga kraft": 4}
        dialog = MosaicDialog(None, {"db": conn})
        self.assertIn("dp_a", dialog.error.text())
        self.assertFalse(dialog.open_button.isEnabled())
        dialog.schema.setCurrentIndex(dialog.schema.findData("dp_b"))
        self.assertEqual(dialog.error.text(), "")
        self.assertTrue(dialog.open_button.isEnabled())

    def test_a_database_without_plugin_schemas_says_so(self):
        dialog = MosaicDialog(None, {"db": FakeConnection()})
        self.assertIn("inga scheman", dialog.error.text())
        self.assertFalse(dialog.open_button.isEnabled())


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PluginMosaicTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)

    def test_it_is_not_a_separate_menu_choice_only_a_button_in_the_database_dialog(self):
        texts = [a.text() for a in self.plugin.actions]
        self.assertFalse([t for t in texts if "planmosaik" in t.lower()], texts)

    def test_it_is_started_from_the_database_dialog_not_from_the_open_menu(self):
        with mock.patch.object(storage, "postgis_connections", return_value={"db": FakeConnection()}), \
                mock.patch("rita_detaljplan.plugin.DatabaseManagerDialog") as dialog_cls, \
                mock.patch.object(self.plugin, "open_mosaic") as open_mosaic, \
                mock.patch("rita_detaljplan.plugin.load_plan") as load:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = True
            dialog.mosaic_requested = True
            dialog.mosaic_target.return_value = ("db", "dp_a")
            self.plugin.open_database_manager()
        open_mosaic.assert_called_once_with("db", "dp_a")
        load.assert_not_called()  # inga planer öppnas

    def test_without_a_database_connection_the_user_is_told(self):
        with mock.patch.object(storage, "postgis_connections", return_value={}), \
                mock.patch("rita_detaljplan.plugin.MosaicDialog") as dialog_cls:
            self.plugin.open_mosaic()
        dialog_cls.assert_not_called()
        self.assertIn("PostgreSQL-anslutning", self.messages()[-1])

    def test_the_chosen_schema_and_statuses_are_loaded_and_the_map_zooms_to_it(self):
        extent = QgsRectangle(0, 0, 1000, 1000)
        with mock.patch.object(storage, "postgis_connections", return_value={"db": FakeConnection()}), \
                mock.patch("rita_detaljplan.plugin.MosaicDialog") as dialog_cls, \
                mock.patch.object(mosaic, "load_mosaic", return_value=mock.Mock()) as load, \
                mock.patch.object(mosaic, "full_extent", return_value=extent), \
                mock.patch.object(self.canvas, "setExtent") as set_extent:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = True
            dialog.selection.return_value = ("db", "dp_a", ["antagen", "laga kraft"])
            dialog.plan_count.return_value = 14
            self.plugin.open_mosaic()
        load.assert_called_once_with(QgsProject.instance(), "db", "dp_a", ["antagen", "laga kraft"])
        set_extent.assert_called_once_with(extent)
        self.assertIn("14 planer", self.messages()[-1])

    def test_a_schema_that_cannot_be_read_gives_an_error_and_unfreezes_the_map(self):
        with mock.patch.object(storage, "postgis_connections", return_value={"db": FakeConnection()}), \
                mock.patch("rita_detaljplan.plugin.MosaicDialog") as dialog_cls, \
                mock.patch.object(mosaic, "load_mosaic", side_effect=ValueError("Schemat är för gammalt")), \
                mock.patch.object(self.canvas, "freeze", wraps=self.canvas.freeze) as freeze:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = True
            dialog.selection.return_value = ("db", "dp_a", ["laga kraft"])
            self.plugin.open_mosaic()
        self.assertIn("för gammalt", self.messages()[-1])
        self.assertEqual(freeze.call_args_list[-1].args, (False,))
        self.assertFalse(self.canvas.isFrozen())


if __name__ == "__main__":
    unittest.main()
