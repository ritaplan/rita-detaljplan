"""Delade ytor, flyttbar text och textverktyget (kräver QGIS)."""
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, RIGHT, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from osgeo import ogr
    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsPalLayerSettings, \
        QgsPointXY, QgsProject, QgsRectangle
    from qgis.PyQt.QtCore import Qt
    from rita_detaljplan.core import geopackage, model
    from rita_detaljplan.core.project import create_plan_project, load_plan
    from rita_detaljplan.core.symbology import UNASSIGNED, _SYMBOL_CLASS, _USE_CLASS
    from test_toolbar import GuiCase
    from test_symbology_render import RenderCase, is_dark


class SplitCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.build_plan(uses=(PLAN,))
        pump()

    def assigned_use(self):
        use = self.features("anvandning_yta")[0]
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", use.id(), entry, filled(entry))
        return self.layers["anvandning_yta"].getFeature(use.id())

    def split(self, table, x=50.0):
        layer = self.layers[table]
        result = layer.splitFeatures([QgsPointXY(x, -10), QgsPointXY(x, 110)])
        self.assertEqual(int(result), 0)
        pump()
        return sorted(layer.getFeatures(), key=lambda f: f.geometry().centroid().asPoint().x())

    def klass(self, feature, expression):
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.layers["detaljplan"]))
        context.setFeature(feature)
        return QgsExpression(expression).evaluate(context)


class SplitTests(SplitCase):
    def test_a_use_split_in_two_keeps_its_provision_on_both_parts(self):
        self.assigned_use()
        left, right = self.split("anvandning_yta")
        for part in (left, right):
            self.assertEqual(part["bestammelser"], 1)
            self.assertEqual(part["beteckning"], "J")
            self.assertTrue(part["farg"])
            self.assertEqual(part["anvandningsform"], "Kvartersmark")

    def test_both_parts_look_assigned_and_have_the_same_colour(self):
        self.assigned_use()
        parts = self.split("anvandning_yta")
        classes = [self.klass(f, _USE_CLASS) for f in parts]
        self.assertEqual(classes, ["Blågrå", "Blågrå"])

    def test_the_parts_have_different_identities_and_each_owns_a_copy_of_the_rows(self):
        self.assigned_use()
        parts = self.split("anvandning_yta")
        ids = [f["objektidentitet"] for f in parts]
        self.assertTrue(all(ids) and ids[0] != ids[1])
        for part in parts:
            rows = self.controller.rows_of("anvandning_yta", part.id())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["yta"], part["objektidentitet"])
        self.assertNotEqual(*[self.controller.rows_of("anvandning_yta", f.id())[0]["objektidentitet"] for f in parts])

    def test_a_use_with_several_provisions_keeps_all_of_them_on_both_parts_in_the_same_order(self):
        use = self.assigned_use()
        other = next(e for e in self.catalog.search(layer="anvandning_yta")
                     if e.anvandningsform == "Kvartersmark" and e.label_base == "B")
        self.controller.add_bestammelse("anvandning_yta", use.id(), other, filled(other))
        original = self.layers["anvandning_yta"].getFeature(use.id())["beteckning"]
        parts = self.split("anvandning_yta")
        self.assertEqual([f["beteckning"] for f in parts], [original, original])
        self.assertEqual([len(self.controller.rows_of("anvandning_yta", f.id())) for f in parts], [2, 2])

    def test_a_split_property_area_keeps_its_provision_on_both_parts_too(self):
        self.assigned_use()
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 90 10, 90 40, 10 40, 10 10)))")
        entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.controller.add_bestammelse("egenskap_yta", prop.id(), entry, filled(entry))
        parts = self.split("egenskap_yta")
        self.assertEqual([f["bestammelser"] for f in parts], [1, 1])
        self.assertEqual([self.klass(f, _SYMBOL_CLASS) for f in parts].count(UNASSIGNED), 0)

    def test_a_split_area_without_provisions_stays_without_them(self):
        parts = self.split("anvandning_yta")
        self.assertEqual([f["bestammelser"] for f in parts], [0, 0])

    def test_the_new_part_starts_with_automatic_text_placement(self):
        use = self.assigned_use()
        self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(20, 20))
        parts = self.split("anvandning_yta")
        with_position = [f for f in parts if f["label_x"] is not None]
        self.assertEqual(len(with_position), 1, "bara en del behåller det flyttade läget")

    def test_a_pasted_copy_with_the_same_identity_gets_its_own(self):
        use = self.assigned_use()
        self.add("anvandning_yta", "MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))",
                 objektidentitet=use["objektidentitet"])
        pump()
        ids = [f["objektidentitet"] for f in self.layers["anvandning_yta"].getFeatures()]
        self.assertEqual(len(ids), len(set(ids)))


class SplitCascadeTests(SplitCase):
    """Delas en yta delas allt med lägre hierarki som ligger på båda sidor om delningen på samma ställe."""
    PROP = "MultiPolygon(((30 20, 70 20, 70 40, 30 40, 30 20)))"  # ligger över x = 50
    LEFT_PROP = "MultiPolygon(((5 60, 25 60, 25 80, 5 80, 5 60)))"  # ligger helt till vänster
    LINE = "MultiLineString(((20 50, 80 50)))"

    def setUp(self):
        super().setUp()
        self.assigned_use()
        self.prop_entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.line_entry = pick(self.catalog, layer="egenskap_linje")
        self.prop = self.draw("egenskap_yta", self.PROP)
        self.left_prop = self.draw("egenskap_yta", self.LEFT_PROP)
        self.line = self.draw("egenskap_linje", self.LINE)
        for table, feature, entry in (("egenskap_yta", self.prop, self.prop_entry),
                                      ("egenskap_yta", self.left_prop, self.prop_entry),
                                      ("egenskap_linje", self.line, self.line_entry)):
            self.controller.add_bestammelse(table, feature.id(), entry, filled(entry))
        pump()
        self.warnings.clear()

    def features_of(self, table):
        return sorted(self.layers[table].getFeatures(), key=lambda f: f.geometry().centroid().asPoint().x())

    def area(self, table):
        return sum(f.geometry().area() for f in self.layers[table].getFeatures())

    def test_splitting_a_use_splits_the_property_that_lies_on_both_parts(self):
        before = self.area("egenskap_yta")
        self.split("anvandning_yta")
        props = self.features_of("egenskap_yta")
        self.assertEqual(len(props), 3, "den korsande egenskapsytan blev två, den andra ligger kvar")
        self.assertAlmostEqual(self.area("egenskap_yta"), before, delta=0.01)
        crossing = [f for f in props if f.geometry().boundingBox().xMinimum() >= 29.9
                    and f.geometry().boundingBox().xMaximum() <= 70.1]
        self.assertEqual(len(crossing), 2)
        for f in crossing:
            box = f.geometry().boundingBox()
            self.assertTrue(box.xMaximum() <= 50.01 or box.xMinimum() >= 49.99, "en del på varje sida om delningen")
            self.assertAlmostEqual(f.geometry().area(), 20 * 20, delta=0.01)

    def test_each_part_belongs_to_the_use_on_its_own_side(self):
        left_use, right_use = self.split("anvandning_yta")
        for use in (left_use, right_use):
            for prop in self.layers["egenskap_yta"].getFeatures():
                inside = prop.geometry().intersection(use.geometry()).area()
                self.assertTrue(inside < 0.01 or abs(inside - prop.geometry().area()) < 0.01,
                                "varje egenskapsyta ligger helt inom en användning")

    def test_the_parts_keep_the_provisions_and_get_identities_of_their_own(self):
        self.split("anvandning_yta")
        props = self.features_of("egenskap_yta")
        ids = [f["objektidentitet"] for f in props]
        self.assertEqual(len(ids), len(set(ids)))
        for f in props:
            self.assertEqual(f["bestammelser"], 1, "delarna behåller bestämmelsen")
            self.assertEqual(len(self.controller.rows_of("egenskap_yta", f.id())), 1)

    def test_a_line_over_both_parts_is_split_too(self):
        self.split("anvandning_yta")
        lines = self.features_of("egenskap_linje")
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(sum(f.geometry().length() for f in lines), 60.0, delta=0.01)
        self.assertTrue(all(f["bestammelser"] == 1 for f in lines))

    def test_a_split_use_with_a_property_keeps_both_kinds_of_provisions_on_both_sides(self):
        use_parts = self.split("anvandning_yta")
        for use in use_parts:
            self.assertEqual(len(self.controller.rows_of("anvandning_yta", use.id())), 1, "användningsbestämmelsen följer med")
        for prop in self.layers["egenskap_yta"].getFeatures():
            self.assertEqual(len(self.controller.rows_of("egenskap_yta", prop.id())), 1, "egenskapsbestämmelsen också")

    def test_the_user_is_told_what_was_split(self):
        self.split("anvandning_yta")
        self.assertTrue(any("Delade även 1 egenskapsyta och 1 egenskapslinje" in w for w in self.warnings), self.warnings)

    def test_what_lies_on_one_side_only_is_left_alone(self):
        untouched = self.left_prop["objektidentitet"]
        self.split("anvandning_yta")
        same = [f for f in self.layers["egenskap_yta"].getFeatures() if f["objektidentitet"] == untouched]
        self.assertEqual(len(same), 1)
        self.assertAlmostEqual(same[0].geometry().area(), 20 * 20, delta=0.01)

    def test_splitting_a_property_area_does_not_split_anything_else(self):
        uses_before = self.layers["anvandning_yta"].featureCount()
        self.split("egenskap_yta")
        self.assertEqual(self.layers["anvandning_yta"].featureCount(), uses_before)
        self.assertEqual(self.layers["egenskap_linje"].featureCount(), 1)

    def test_splitting_the_plan_area_splits_uses_properties_and_lines(self):
        plans = self.split("detaljplan")
        self.assertEqual(len(plans), 2)
        self.assertNotEqual(plans[0]["objektidentitet"], plans[1]["objektidentitet"])
        uses = self.features_of("anvandning_yta")
        self.assertEqual(len(uses), 2)
        self.assertTrue(all(f["bestammelser"] == 1 for f in uses), "delarna av användningen behåller bestämmelsen")
        self.assertEqual(len(self.features_of("egenskap_yta")), 3)
        self.assertEqual(len(self.features_of("egenskap_linje")), 2)
        self.assertAlmostEqual(self.area("anvandning_yta"), 10000.0, delta=0.5)

    def test_after_a_plan_split_every_part_lies_within_one_plan_area_and_one_use(self):
        plans = self.split("detaljplan")
        for layer_name in ("anvandning_yta", "egenskap_yta"):
            for f in self.layers[layer_name].getFeatures():
                hits = [p for p in plans if p.geometry().buffer(0.01, 4).contains(f.geometry())]
                self.assertEqual(len(hits), 1, layer_name)

    def test_two_cuts_give_three_parts_below_as_well(self):
        layer = self.layers["anvandning_yta"]
        for x in (40.0, 60.0):
            self.assertEqual(int(layer.splitFeatures([QgsPointXY(x, -10), QgsPointXY(x, 110)])), 0)
            pump()
        self.assertEqual(layer.featureCount(), 3)
        props = self.features_of("egenskap_yta")
        self.assertEqual(len(props), 4, "den korsande egenskapsytan (x 30-70) delas i tre, plus den på vänster sida")
        self.assertAlmostEqual(self.area("egenskap_yta"), 20 * 40 + 20 * 20, delta=0.01)

    def test_a_pasted_copy_is_not_mistaken_for_a_split(self):
        use = self.features_of("anvandning_yta")[0]
        self.add("anvandning_yta", "MultiPolygon(((0 0, 50 0, 50 100, 0 100, 0 0)))",
                 objektidentitet=use["objektidentitet"])
        pump()
        self.assertEqual(self.layers["egenskap_yta"].featureCount(), 2, "inget delades")


class SchemaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_the_area_layers_have_hidden_plugin_only_position_fields(self):
        for layer_def in model.AREA_LAYERS:
            names = [f.name for f in layer_def.fields]
            self.assertIn("label_x", names)
            self.assertIn("label_y", names)
        self.assertLessEqual({"label_x", "label_y"}, set(model.PLUGIN_ONLY_FIELDS))

    def test_a_schema_4_plan_gets_the_position_fields(self):
        gpkg, _ = create_plan_project(self.dir, "gammal", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            layer = ds.GetLayerByName(name)
            for field in ("label_x", "label_y"):
                layer.DeleteField(layer.GetLayerDefn().GetFieldIndex(field))
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='4' WHERE key='schema_version'")
        con.commit()
        con.close()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            self.assertGreaterEqual(layers[name].fields().indexOf("label_x"), 0, name)
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_a_schema_6_plan_gets_the_text_width_and_the_secondary_boundary_field(self):
        gpkg, _ = create_plan_project(self.dir, "sex", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            layer = ds.GetLayerByName(name)
            layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("label_w"))
        layer = ds.GetLayerByName("egenskap_yta")
        layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("sekundar"))
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='6' WHERE key='schema_version'")
        con.commit()
        con.close()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            self.assertGreaterEqual(layers[name].fields().indexOf("label_w"), 0, name)
        self.assertGreaterEqual(layers["egenskap_yta"].fields().indexOf("sekundar"), 0)
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_a_schema_11_plan_gets_the_text_angle_on_every_area_layer(self):
        gpkg, _ = create_plan_project(self.dir, "elva", "Eskilstuna", "0484", 3006)
        tables = ("anvandning_yta", "egenskap_yta", "egenskap_linje", "egenskap_punkt")
        ds = ogr.Open(str(gpkg), 1)
        for name in tables:
            layer = ds.GetLayerByName(name)
            layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("label_rot"))
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='11' WHERE key='schema_version'")
        con.commit()
        con.close()
        self.assertTrue(geopackage.upgrade(gpkg))
        project = QgsProject()
        layers = load_plan(gpkg, project)
        for name in tables:
            self.assertGreaterEqual(layers[name].fields().indexOf("label_rot"), 0, name)
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))
        self.assertEqual(model.SCHEMA_VERSION, 12)

    def test_the_postgis_upgrade_adds_the_text_angle_only_to_schemas_older_than_12(self):
        from rita_detaljplan.core import storage
        old = " ".join(storage.postgis_upgrade("dp", 11, 3010))
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje", "egenskap_punkt"):
            self.assertIn(f'ALTER TABLE "dp"."{name}" ADD COLUMN IF NOT EXISTS "label_rot"', old)
        self.assertLess(old.index('"label_rot"'), old.index("SET \"value\""), "versionen skrivs sist")
        current = " ".join(storage.postgis_upgrade("dp", model.SCHEMA_VERSION, 3010))
        self.assertNotIn("label_rot", current)
        from_start = " ".join(storage.postgis_upgrade("dp", 3, 3010))
        self.assertEqual(from_start.count('ADD COLUMN IF NOT EXISTS "label_rot"'), 4, "en gång per ytlager")

    def test_the_new_fields_are_hidden_plugin_only_fields(self):
        self.assertLessEqual({"label_w", "label_rot", "sekundar"}, set(model.PLUGIN_ONLY_FIELDS))

    def test_an_up_to_date_plan_is_left_alone(self):
        gpkg, _ = create_plan_project(self.dir, "ny", "Eskilstuna", "0484", 3006)
        self.assertFalse(geopackage.upgrade(gpkg))


class LabelPlacementTests(RenderCase):
    def test_every_label_layer_can_be_moved_by_its_position_fields(self):
        for table in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            labeling = self.layers[table].labeling()  # måste hållas vid liv så länge inställningarna används
            settings = labeling.settings()
            props = settings.dataDefinedProperties()
            self.assertEqual(props.property(QgsPalLayerSettings.Property.PositionX).field(), "label_x", table)
            self.assertEqual(props.property(QgsPalLayerSettings.Property.PositionY).field(), "label_y", table)
            self.assertTrue(props.isActive(QgsPalLayerSettings.Property.PositionX), table)

    def label_pixels(self, **attrs):
        plan = "MultiPolygon(((0 0, 100 0, 100 60, 0 60, 0 0)))"
        self.add("detaljplan", plan)
        self.add("anvandning_yta", plan, bestammelser=1, farg="Gul", beteckning="BC", **attrs)
        image = self.render(self.in_map_order(["anvandning_yta"]), extent=(-5, -5, 105, 65), size=440)
        pts = [(x, y) for x in range(440) for y in range(440) if is_dark(image.pixelColor(x, y))
               and 20 < x < 420 and 20 < y < 420]
        return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)) if pts else None

    def test_a_moved_text_is_drawn_at_its_new_position(self):
        default = self.label_pixels()
        self.assertIsNotNone(default)
        for layer in self.layers.values():
            if layer.isSpatial():
                layer.rollBack()
                layer.startEditing()
                for fid in layer.allFeatureIds():
                    layer.deleteFeature(fid)
        moved = self.label_pixels(label_x=15.0, label_y=10.0)
        self.assertIsNotNone(moved)
        self.assertLess(moved[0], default[0] - 100, "flyttad åt vänster")
        self.assertGreater(moved[1], default[1] + 40, "flyttad nedåt (bildens y växer nedåt)")


class PropertyPointLabelTests(RenderCase):
    """En egenskapspunkts text står alltid intill punkten: ingen prick, ingen ledlinje, ingen flytt."""

    def settings(self):
        labeling = self.layers["egenskap_punkt"].labeling()  # måste hållas vid liv så länge inställningarna används
        return labeling, labeling.settings()

    def test_the_text_cannot_be_moved_by_position_fields(self):
        _labeling, settings = self.settings()
        props = settings.dataDefinedProperties()
        self.assertFalse(props.isActive(QgsPalLayerSettings.Property.PositionX))
        self.assertFalse(props.isActive(QgsPalLayerSettings.Property.PositionY))

    def test_there_is_no_leader_line(self):
        _labeling, settings = self.settings()
        callout = settings.callout()
        self.assertTrue(callout is None or not callout.enabled())

    def test_the_dot_is_only_drawn_while_the_point_is_selected(self):
        """Annars syns punkten inte, och en markerad punkt som ska tas bort kan inte ses."""
        from qgis.core import QgsSymbolLayer
        dot = next(c for c in self.layers["egenskap_punkt"].renderer().categories() if c.value() == "")
        prop = dot.symbol().symbolLayer(0).dataDefinedProperties().property(QgsSymbolLayer.Property.LayerEnabled)
        self.assertTrue(prop.isActive())
        self.assertEqual(prop.expressionString(), "is_selected()")

    def test_points_are_not_among_the_movable_texts(self):
        from rita_detaljplan.controller import LABEL_TABLES
        self.assertNotIn("egenskap_punkt", LABEL_TABLES)


class PropertyPointMoveTests(SplitCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.select_tool import SelectTool
        self.select_tool = SelectTool(self.canvas, self.controller, lambda candidates: candidates[0],
                                      lambda *a: None)
        self.addCleanup(self.select_tool.deleteLater)

    def point_text(self, fid, table="egenskap_punkt", unplaced=False):
        return SimpleNamespace(layerID=self.layers[table].id(), featureId=fid, labelRect=QgsRectangle(0, 0, 1, 1),
                               isUnplaced=unplaced)

    def test_clicking_the_text_selects_the_point_so_it_can_be_removed(self):
        point = self.draw("egenskap_punkt", "MultiPoint((20 30))")
        results = SimpleNamespace(labelsAtPosition=lambda p: [self.point_text(point.id())])
        with mock.patch.object(self.canvas, "labelingResults", return_value=results):
            chosen = self.select_tool.click(QgsPointXY(21, 31))
        self.assertEqual((chosen.table, chosen.fid), ("egenskap_punkt", point.id()))
        self.assertEqual(self.layers["egenskap_punkt"].selectedFeatureIds(), [point.id()])

    def test_a_rectangle_around_the_text_selects_the_point(self):
        point = self.draw("egenskap_punkt", "MultiPoint((20 30))")
        results = SimpleNamespace(labelsWithinRect=lambda r: [self.point_text(point.id()),
                                                              self.point_text(99, unplaced=True)])
        with mock.patch.object(self.canvas, "labelingResults", return_value=results):
            found = self.select_tool.select_rect(QgsRectangle(21, 31, 25, 33))
        self.assertIn(("egenskap_punkt", point.id()), [(c.table, c.fid) for c in found])
        self.assertNotIn(("egenskap_punkt", 99), [(c.table, c.fid) for c in found], "en text utan plats räknas inte")
        self.assertEqual(self.layers["egenskap_punkt"].selectedFeatureIds(), [point.id()])

    def test_the_point_itself_can_still_be_selected_and_deleted(self):
        point = self.draw("egenskap_punkt", "MultiPoint((20 30))")
        self.select_tool.click(QgsPointXY(20, 30))
        layer = self.layers["egenskap_punkt"]
        self.assertEqual(layer.selectedFeatureIds(), [point.id()])
        layer.deleteSelectedFeatures()
        pump()
        self.assertEqual(layer.featureCount(), 0)

    def test_the_controller_refuses_to_move_a_points_text(self):
        point = self.draw("egenskap_punkt", "MultiPoint((20 30))")
        self.assertIsNone(self.controller.move_label("egenskap_punkt", point.id(), QgsPointXY(35, 40)))
        self.assertIsNone(self.layers["egenskap_punkt"].getFeature(point.id())["label_x"])


class LabelToolCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.uses = self.build_plan(uses=(LEFT, RIGHT))
        self.tool = __import__("rita_detaljplan.gui.label_tool", fromlist=["LabelTool"]).LabelTool(
            self.canvas, self.controller, lambda text, warning=False: self.reports.append((text, warning)))
        self.reports = []
        self.addCleanup(self.tool.deleteLater)
        self.LabelRef = __import__("rita_detaljplan.gui.label_tool", fromlist=["LabelRef"]).LabelRef
        left, right = self.uses
        self.left_label = self.ref("anvandning_yta", left, QgsRectangle(20, 45, 30, 55))
        self.right_label = self.ref("anvandning_yta", right, QgsRectangle(70, 45, 80, 55))
        self.labels = [self.left_label, self.right_label]
        self.tool.labels_at = lambda p: [l for l in self.labels if l.rect.contains(p)]
        self.tool.labels_in = lambda r: [l for l in self.labels if r.contains(l.rect)]
        self.canvas.setExtent(QgsRectangle(0, 0, 100, 100))  # 0,25 m per bildpunkt: handtag 2 m, rotationszon 2-5,5 m

    def ref(self, table, feature, rect):
        return self.LabelRef(table, feature.id(), rect)

    def drag(self, start, end, shift=False):
        self.tool.press(QgsPointXY(*start), shift)
        self.tool.drag_to(QgsPointXY(*end))
        self.tool.release(QgsPointXY(*end))


class LabelToolTests(LabelToolCase):
    def test_a_click_on_a_text_selects_it(self):
        self.drag((25, 50), (25, 50))
        self.assertEqual([l.key for l in self.tool.selected], [self.left_label.key])

    def test_a_click_on_another_text_replaces_the_selection_and_shift_adds(self):
        self.drag((25, 50), (25, 50))
        self.drag((75, 50), (75, 50))
        self.assertEqual([l.key for l in self.tool.selected], [self.right_label.key])
        self.drag((25, 50), (25, 50), shift=True)
        self.assertEqual(len(self.tool.selected), 2)

    def test_a_click_on_empty_ground_clears_the_selection(self):
        self.drag((25, 50), (25, 50))
        self.drag((50, 90), (50, 90))
        self.assertEqual(self.tool.selected, [])

    def test_dragging_from_empty_ground_selects_the_texts_inside_the_rectangle(self):
        self.drag((10, 40), (35, 60))
        self.assertEqual([l.key for l in self.tool.selected], [self.left_label.key])
        self.drag((10, 40), (90, 60))
        self.assertEqual(len(self.tool.selected), 2)

    def test_a_rectangle_around_nothing_reports_it(self):
        self.drag((45, 5), (55, 10))
        self.assertEqual(self.tool.selected, [])
        self.assertTrue(any("Ingen text" in text for text, _ in self.reports))

    def test_shift_rectangle_adds_to_the_selection(self):
        self.drag((25, 50), (25, 50))
        self.drag((60, 40), (90, 60), shift=True)
        self.assertEqual(len(self.tool.selected), 2)

    def test_dragging_a_text_moves_it_and_writes_the_position(self):
        self.drag((25, 50), (30, 30))
        layer = self.layers["anvandning_yta"]
        feature = layer.getFeature(self.left_label.fid)
        self.assertAlmostEqual(feature["label_x"], 30.0)  # textens mitt (25, 50) flyttades (+5, -20)
        self.assertAlmostEqual(feature["label_y"], 30.0)

    def test_the_moved_text_is_kept_selected_at_its_new_place(self):
        self.drag((25, 50), (30, 30))
        self.assertEqual(len(self.tool.selected), 1)
        self.assertAlmostEqual(self.tool.selected[0].rect.center().y(), 30.0)

    def test_every_selected_text_moves_the_same_distance(self):
        self.drag((10, 40), (90, 60))
        self.drag((25, 50), (25, 30))
        layer = self.layers["anvandning_yta"]
        self.assertAlmostEqual(layer.getFeature(self.left_label.fid)["label_y"], 30.0)
        self.assertAlmostEqual(layer.getFeature(self.right_label.fid)["label_y"], 30.0)
        self.assertAlmostEqual(layer.getFeature(self.right_label.fid)["label_x"], 75.0)

    def test_a_text_can_be_moved_outside_its_area(self):
        self.drag((25, 50), (90, 50))  # den vänstra ytan slutar vid x = 50
        feature = self.layers["anvandning_yta"].getFeature(self.left_label.fid)
        self.assertAlmostEqual(feature["label_x"], 90.0)
        self.assertAlmostEqual(feature["label_y"], 50.0)
        from qgis.core import QgsGeometry
        self.assertFalse(feature.geometry().intersects(
            QgsGeometry.fromPointXY(QgsPointXY(feature["label_x"], feature["label_y"]))))

    def test_a_click_without_dragging_moves_nothing(self):
        self.drag((25, 50), (25, 50))
        self.assertIsNone(self.layers["anvandning_yta"].getFeature(self.left_label.fid)["label_x"])

    def test_moving_needs_an_edit_session(self):
        self.controller.stop_editing(save=False)
        self.tool.selected = [self.left_label]
        self.assertEqual(self.tool.move_selected(5, 5), 0)
        self.assertTrue(any("pennan" in text and warning for text, warning in self.reports))

    def test_delete_returns_the_selected_texts_to_automatic_placement(self):
        self.drag((25, 50), (30, 30))
        self.assertEqual(self.tool.reset_selected(), 1)
        feature = self.layers["anvandning_yta"].getFeature(self.left_label.fid)
        self.assertIsNone(feature["label_x"])
        self.assertEqual(self.tool.selected, [])

    def test_escape_clears_the_selection(self):
        from qgis.PyQt.QtGui import QKeyEvent
        from qgis.PyQt.QtCore import QEvent
        self.drag((25, 50), (25, 50))
        self.tool.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.tool.selected, [])

    def test_only_our_label_layers_count(self):
        results = SimpleNamespace(labelsAtPosition=lambda p: [
            SimpleNamespace(layerID=self.layers["anvandning_yta"].id(), featureId=7, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=False),
            SimpleNamespace(layerID=self.layers["detaljplan"].id(), featureId=1, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=False),
            SimpleNamespace(layerID=self.layers["anvandning_yta"].id(), featureId=8, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=True),
            SimpleNamespace(layerID="okänt", featureId=9, labelRect=QgsRectangle(0, 0, 1, 1), isUnplaced=False)])
        tool = type(self.tool)(self.canvas, self.controller, lambda *a: None)
        self.addCleanup(tool.deleteLater)
        with mock.patch.object(self.canvas, "labelingResults", return_value=results):
            found = tool.labels_at(QgsPointXY(0, 0))
        self.assertEqual([(l.table, l.fid) for l in found], [("anvandning_yta", 7)])

    def test_without_a_drawn_map_there_are_no_texts(self):
        tool = type(self.tool)(self.canvas, self.controller, lambda *a: None)
        self.addCleanup(tool.deleteLater)
        self.assertEqual(tool.labels_at(QgsPointXY(1, 1)), [])


class LabelResizeTests(LabelToolCase):
    """Textrutan för egenskapsbestämmelser omformas genom att dra i hörnen; bokstävernas storlek ändras aldrig."""

    def setUp(self):
        super().setUp()
        self.canvas.setExtent(QgsRectangle(0, 0, 100, 100))  # 0,25 m per bildpunkt: hörnens träffyta blir 2 m
        self.prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        self.prop_label = self.ref("egenskap_yta", self.prop, QgsRectangle(15, 20, 35, 30))
        self.labels.append(self.prop_label)
        self.layer = self.layers["egenskap_yta"]

    def values(self, table="egenskap_yta", fid=None):
        feature = self.layers[table].getFeature(self.prop.id() if fid is None else fid)
        return feature["label_x"], feature["label_y"], feature["label_w"]

    def test_dragging_a_corner_of_a_selected_text_sets_its_width_and_middle(self):
        self.drag((25, 25), (25, 25))
        self.assertEqual([l.key for l in self.tool.selected], [self.prop_label.key])
        self.drag((35, 30), (30, 34))  # övre högra hörnet mot det motsatta (15, 20) som ligger fast
        x, y, w = self.values()
        self.assertAlmostEqual(w, 15.0)
        self.assertAlmostEqual(x, 22.5)
        self.assertAlmostEqual(y, 27.0)

    def test_the_selection_follows_the_new_shape(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        (label,) = self.tool.selected
        self.assertEqual((label.rect.xMinimum(), label.rect.xMaximum()), (15.0, 30.0))

    def test_a_corner_only_works_on_a_text_that_is_already_selected(self):
        self.drag((35, 30), (30, 34))  # texten är inte markerad: klicket träffar bara texten och flyttar den
        self.assertIsNone(self.values()[2])

    def test_the_text_of_a_use_can_be_reshaped_too(self):
        self.drag((25, 50), (25, 50))
        self.drag((30, 55), (35, 60))  # hörnet på användningens text (20-30, 45-55) dras utåt
        x, y, w = self.values("anvandning_yta", self.uses[0].id())
        self.assertAlmostEqual(w, 15.0, msg="bredden sattes av hörndraget (inte en flytt)")
        self.assertIsNotNone(x)

    def test_the_size_of_the_letters_is_never_changed_by_reshaping(self):
        from qgis.core import QgsPalLayerSettings
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        settings = self.layer.labeling().settings()
        self.assertFalse(settings.dataDefinedProperties().isActive(QgsPalLayerSettings.Property.Size))
        self.assertFalse(settings.dataDefinedProperties().isActive(QgsPalLayerSettings.Property.FontSizeUnit))

    def test_a_tiny_rectangle_still_gets_a_usable_width(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (15.2, 20.2))
        self.assertGreaterEqual(self.values()[2], self.controller.MIN_LABEL_WIDTH)

    def test_a_click_on_a_corner_without_dragging_changes_nothing(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (35, 30))
        self.assertEqual(self.values(), (None, None, None))

    def test_reshaping_needs_an_edit_session(self):
        self.drag((25, 25), (25, 25))
        self.controller.stop_editing(save=False)
        self.reports.clear()
        self.assertFalse(self.tool.resize_label(self.prop_label, QgsRectangle(15, 20, 30, 34)))
        self.assertTrue(self.reports and self.reports[-1][1])

    def test_delete_gives_the_text_its_original_shape_back(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        self.tool.reset_selected()
        self.assertEqual(self.values(), (None, None, None))

    def test_the_handles_are_shown_for_a_selected_use_or_property_text(self):
        self.drag((25, 25), (25, 25))
        self.assertEqual(self.tool._handles.numberOfVertices(), 4)
        self.drag((25, 50), (25, 50))
        self.assertEqual(self.tool._handles.numberOfVertices(), 4, "användningens text har också handtag")

    def test_dragging_a_corner_of_a_use_text_sets_its_width_too(self):
        self.drag((25, 50), (25, 50))  # markera användningens text (rutan 20-30, 45-55)
        self.drag((30, 55), (35, 60))  # övre högra hörnet ut
        feature = self.layers["anvandning_yta"].getFeature(self.left_label.fid)
        self.assertAlmostEqual(feature["label_w"], 15.0)
        self.assertAlmostEqual(feature["label_x"], 27.5)


class LabelControllerTests(SplitCase):
    def test_move_label_writes_the_position_and_reset_clears_it(self):
        use = self.features("anvandning_yta")[0]
        self.assertEqual(self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(30, 40)), QgsPointXY(30, 40))
        moved = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertEqual((moved["label_x"], moved["label_y"]), (30.0, 40.0))
        self.controller.reset_label("anvandning_yta", use.id())
        self.assertIsNone(self.layers["anvandning_yta"].getFeature(use.id())["label_x"])

    def test_an_outside_position_is_kept_as_is(self):
        use = self.features("anvandning_yta")[0]
        point = self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(150, 50))
        self.assertAlmostEqual(point.x(), 150.0)
        self.assertAlmostEqual(point.y(), 50.0)
        moved = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertAlmostEqual(moved["label_x"], 150.0)

    def test_a_missing_area_is_ignored(self):
        self.assertIsNone(self.controller.move_label("anvandning_yta", 9999, QgsPointXY(1, 1)))


class ResizeLabelControllerTests(SplitCase):
    def test_resize_label_writes_width_and_middle_and_reset_clears_them(self):
        from qgis.core import QgsRectangle as R
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        point = self.controller.resize_label("egenskap_yta", prop.id(), R(10, 20, 30, 30))
        self.assertEqual((point.x(), point.y()), (20.0, 25.0))
        stored = self.layers["egenskap_yta"].getFeature(prop.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_w"]), (20.0, 25.0, 20.0))
        self.controller.reset_label("egenskap_yta", prop.id())
        stored = self.layers["egenskap_yta"].getFeature(prop.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_w"]), (None, None, None))

    def test_only_use_and_property_areas_have_a_reshapable_text(self):
        from qgis.core import QgsRectangle as R
        self.assertEqual(self.controller.RESIZABLE_LABELS, ("anvandning_yta", "egenskap_yta"))
        use = next(iter(self.layers["anvandning_yta"].getFeatures()))
        point = self.controller.resize_label("anvandning_yta", use.id(), R(0, 0, 10, 10))
        self.assertEqual((point.x(), point.y()), (5.0, 5.0))
        self.assertEqual(self.layers["anvandning_yta"].getFeature(use.id())["label_w"], 10.0)
        self.assertIsNone(self.controller.resize_label("detaljplan", 1, R(0, 0, 10, 10)))
        self.assertIsNone(self.controller.resize_label("egenskap_yta", 9999, R(0, 0, 10, 10)))

    def test_a_new_or_split_area_starts_without_a_reshaped_text(self):
        from rita_detaljplan.core import assignments
        from rita_detaljplan.core.project import apply_attributes
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        apply_attributes(self.layers["egenskap_yta"], [prop.id()], {"label_w": 12.0})
        assignments.reset_new_area(self.controller.project, "egenskap_yta", prop.id())
        self.assertIsNone(self.layers["egenskap_yta"].getFeature(prop.id())["label_w"])


class RotateLabelControllerTests(SplitCase):
    def test_rotate_label_writes_the_angle_clockwise_and_pins_the_text_where_it_is(self):
        use = self.features_of("anvandning_yta")[0]
        angle = self.controller.rotate_label("anvandning_yta", use.id(), 30.0, QgsPointXY(40, 50))
        self.assertEqual(angle, 30.0)
        stored = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertEqual((stored["label_rot"], stored["label_x"], stored["label_y"]), (30.0, 40.0, 50.0))

    def test_an_existing_position_is_kept_when_rotating(self):
        use = self.features_of("anvandning_yta")[0]
        self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(30, 40))
        self.controller.rotate_label("anvandning_yta", use.id(), 45.0, QgsPointXY(99, 99))
        stored = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_rot"]), (30.0, 40.0, 45.0))

    def test_angles_are_stored_between_0_and_360_and_a_horizontal_text_as_empty(self):
        use = self.features_of("anvandning_yta")[0]
        layer = self.layers["anvandning_yta"]
        for given, wanted in ((370.0, 10.0), (-30.0, 330.0)):
            self.assertAlmostEqual(self.controller.rotate_label("anvandning_yta", use.id(), given), wanted)
            self.assertAlmostEqual(layer.getFeature(use.id())["label_rot"], wanted)
        from qgis.core import NULL
        for given in (720.0, 0.0, 360.0, 359.9999999):
            self.assertEqual(self.controller.rotate_label("anvandning_yta", use.id(), given), 0.0)
            self.assertIn(layer.getFeature(use.id())["label_rot"], (None, NULL), given)

    def test_only_the_texts_of_areas_can_be_rotated(self):
        self.assertEqual(self.controller.ROTATABLE_LABELS, ("anvandning_yta", "egenskap_yta"))
        self.assertIsNone(self.controller.rotate_label("egenskap_linje", 1, 30.0))
        self.assertIsNone(self.controller.rotate_label("egenskap_punkt", 1, 30.0))
        self.assertIsNone(self.controller.rotate_label("anvandning_yta", 9999, 30.0))

    def test_reset_label_makes_the_text_horizontal_again(self):
        use = self.features_of("anvandning_yta")[0]
        self.controller.rotate_label("anvandning_yta", use.id(), 30.0, QgsPointXY(40, 50))
        self.controller.reset_label("anvandning_yta", use.id())
        stored = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_rot"]), (None, None, None))

    def test_a_new_or_split_area_starts_without_a_rotation(self):
        from rita_detaljplan.core import assignments
        from rita_detaljplan.core.project import apply_attributes
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        apply_attributes(self.layers["egenskap_yta"], [prop.id()], {"label_rot": 40.0})
        assignments.reset_new_area(self.controller.project, "egenskap_yta", prop.id())
        self.assertIsNone(self.layers["egenskap_yta"].getFeature(prop.id())["label_rot"])

    def features_of(self, table):
        return list(self.layers[table].getFeatures())


class LabelRotateTests(LabelToolCase):
    """Rotera texten med samma verktyg: håll strax utanför ett hörn (rotationspil) och dra. Själva hörnet omformar
    fortfarande rutan."""

    def setUp(self):
        super().setUp()
        self.canvas.setExtent(QgsRectangle(0, 0, 100, 100))  # 0,25 m per bildpunkt: hörnet 2 m, rotationszonen 2-5,5 m
        self.prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        self.prop_label = self.ref("egenskap_yta", self.prop, QgsRectangle(15, 20, 35, 30))
        self.labels.append(self.prop_label)
        self.layer = self.layers["egenskap_yta"]
        self.drag((25, 25), (25, 25))  # markera egenskapens text (mitt (25, 25), 20 x 10 m)

    def values(self, table="egenskap_yta", fid=None):
        feature = self.layers[table].getFeature(self.prop.id() if fid is None else fid)
        return feature["label_x"], feature["label_y"], feature["label_w"], feature["label_rot"]

    @staticmethod
    def around(center, degrees, radius):
        import math
        return (center[0] + radius * math.cos(math.radians(degrees)), center[1] + radius * math.sin(math.radians(degrees)))

    def test_the_zones_are_the_corner_to_resize_and_just_outside_it_to_rotate(self):
        P = QgsPointXY
        self.assertEqual(self.tool.zone_at(P(35, 30)), "resize", "själva hörnet")
        self.assertEqual(self.tool.zone_at(P(37.5, 32.5)), "rotate", "strax utanför hörnet")
        self.assertEqual(self.tool.zone_at(P(13, 18)), "rotate", "och utanför de andra hörnen")
        self.assertIsNone(self.tool.zone_at(P(25, 25)), "inne i rutan")
        self.assertIsNone(self.tool.zone_at(P(37.5, 25)), "längs sidan, långt från hörnen")
        self.assertIsNone(self.tool.zone_at(P(60, 60)), "långt bort")
        self.assertIsNone(self.tool.zone_at(P(33, 28)), "innanför hörnet")
        self.tool.clear()
        self.assertIsNone(self.tool.zone_at(P(37.5, 32.5)), "bara en markerad text har en rotationszon")

    def test_the_text_of_a_use_can_be_both_reshaped_and_rotated(self):
        self.drag((25, 50), (25, 50))  # användningens text (20-30, 45-55)
        self.assertEqual(self.tool.zone_at(QgsPointXY(30, 55)), "resize", "hörnet omformar")
        self.assertEqual(self.tool.zone_at(QgsPointXY(32.5, 57.5)), "rotate")

    def test_dragging_in_the_zone_rotates_the_text_around_its_middle(self):
        start = (37.5, 32.5)
        import math
        first = math.degrees(math.atan2(start[1] - 25, start[0] - 25))
        self.drag(start, self.around((25, 25), first + 90, 15))  # ett kvarts varv moturs
        x, y, w, rot = self.values()
        self.assertAlmostEqual(rot, 270.0, places=6, msg="lagras medurs: 90 grader moturs är 270 medurs")
        self.assertAlmostEqual(x, 25.0)
        self.assertAlmostEqual(y, 25.0, msg="texten fästs där den är och roterar runt sin mitt")
        self.assertIsNone(w, "bredden ändras inte")

    def test_a_clockwise_turn_is_stored_as_the_same_number_of_degrees(self):
        import math
        start = (37.5, 32.5)
        first = math.degrees(math.atan2(start[1] - 25, start[0] - 25))
        self.drag(start, self.around((25, 25), first - 40, 15))
        self.assertAlmostEqual(self.values()[3], 40.0, places=6)

    def test_shift_locks_the_angle_to_steps_of_15_degrees(self):
        import math
        start = (37.5, 32.5)
        first = math.degrees(math.atan2(start[1] - 25, start[0] - 25))
        self.drag(start, self.around((25, 25), first + 37, 15), shift=True)  # 37 grader moturs -> 30 grader
        self.assertAlmostEqual(self.values()[3], 330.0, places=6)

    def test_the_selection_frame_is_turned_with_the_text_and_follows_it(self):
        import math
        start = (37.5, 32.5)
        first = math.degrees(math.atan2(start[1] - 25, start[0] - 25))
        self.drag(start, self.around((25, 25), first + 90, 15))
        (label,) = self.tool.selected
        self.assertAlmostEqual(label.angle, 90.0, places=6)
        box = self.tool._marks.asGeometry().boundingBox()
        self.assertAlmostEqual(box.width(), 10.0, places=6, msg="20 x 10 vriden ett kvarts varv: 10 x 20")
        self.assertAlmostEqual(box.height(), 20.0, places=6)
        self.assertAlmostEqual(box.center().x(), 25.0)
        self.assertAlmostEqual(box.center().y(), 25.0)

    def test_a_click_in_the_zone_without_dragging_changes_nothing_and_keeps_the_selection(self):
        self.drag((37.5, 32.5), (37.5, 32.5))
        self.assertEqual(self.values(), (None, None, None, None))
        self.assertEqual([l.key for l in self.tool.selected], [self.prop_label.key])

    def test_rotating_needs_an_edit_session(self):
        self.controller.stop_editing(save=False)
        self.reports.clear()
        self.assertFalse(self.tool.rotate_label(self.prop_label, 45.0))
        self.assertTrue(self.reports and self.reports[-1][1])

    def test_delete_makes_a_rotated_text_horizontal_and_automatic_again(self):
        self.tool.rotate_label(self.prop_label, 45.0)
        self.assertIsNotNone(self.values()[3])
        self.tool.reset_selected()
        self.assertEqual(self.values(), (None, None, None, None))

    def test_a_rotated_text_can_still_be_moved(self):
        self.tool.rotate_label(self.prop_label, 45.0)
        self.drag((25, 25), (35, 35))
        x, y, _, rot = self.values()
        self.assertAlmostEqual(x, 35.0)
        self.assertAlmostEqual(y, 35.0)
        self.assertAlmostEqual(rot, 315.0, msg="vinkeln behålls när den flyttas")
        self.assertAlmostEqual(self.tool.selected[0].angle, 45.0)

    def test_a_corner_still_reshapes_the_text_box_of_a_turned_text(self):
        turned = self.LabelRef("egenskap_yta", self.prop.id(), QgsRectangle(15, 20, 35, 30), 90.0)
        self.labels[-1] = turned
        self.tool.selected = [turned]
        self.tool._show_selection()
        # ett kvarts varv moturs om (25, 25): hörnet (35, 30) hamnar i (20, 35) och det motsatta (15, 20) i (30, 15)
        self.drag((20, 35), (18, 40))
        x, y, w, rot = self.values()
        self.assertAlmostEqual(w, 25.0, msg="bredden mäts längs den vridna texten")
        self.assertAlmostEqual(x, 24.0)
        self.assertAlmostEqual(y, 27.5)
        self.assertIsNone(rot, "reshapen ändrar inte vinkeln")
        self.assertEqual(self.tool.selected[0].angle, 90.0, "och ramen är fortfarande vriden")

    def test_the_cursor_is_a_rotation_arrow_in_the_zone_a_diagonal_arrow_on_the_corner_and_the_hand_elsewhere(self):
        P = QgsPointXY
        self.tool.update_cursor(P(37.5, 32.5))
        self.assertEqual(self.tool.current_cursor.shape(), Qt.CursorShape.BitmapCursor, "egen rotationspil")
        self.assertFalse(self.tool.current_cursor.pixmap().isNull())
        self.tool.update_cursor(P(35, 30))
        self.assertEqual(self.tool.current_cursor.shape(), Qt.CursorShape.SizeBDiagCursor, "övre högra hörnet: /")
        self.tool.update_cursor(P(35, 20))
        self.assertEqual(self.tool.current_cursor.shape(), Qt.CursorShape.SizeFDiagCursor, "nedre högra hörnet: \\")
        self.tool.update_cursor(P(60, 60))
        self.assertEqual(self.tool.current_cursor.shape(), Qt.CursorShape.PointingHandCursor)

    def test_the_rotation_arrow_is_a_thin_line_and_not_a_filled_blob(self):
        image = self.tool._rotate_cursor.pixmap().toImage()
        size = image.width()
        inked = sum(1 for x in range(size) for y in range(size) if image.pixelColor(x, y).alpha() > 0)
        self.assertEqual(image.pixelColor(size // 2, size // 2).alpha(), 0, "bågens mitt är tom (inte en fylld klump)")
        self.assertLess(inked, size * size * 0.4, "markören täcker mindre än 40 % av sin ruta")

    def test_a_diagonal_cursor_turns_with_a_text_turned_a_quarter(self):
        turned = self.LabelRef("egenskap_yta", self.prop.id(), QgsRectangle(15, 20, 35, 30), 90.0)
        self.tool.selected = [turned]
        self.tool.update_cursor(QgsPointXY(20, 35))  # det som var övre högra hörnet
        self.assertEqual(self.tool.current_cursor.shape(), Qt.CursorShape.SizeFDiagCursor)

    def test_a_rotated_text_from_the_map_is_read_as_its_real_box_and_angle(self):
        self.layer.changeAttributeValue(self.prop.id(), self.layer.fields().indexOf("label_rot"), 30.0)
        position = SimpleNamespace(layerID=self.layer.id(), featureId=self.prop.id(), isUnplaced=False,
                                   labelRect=QgsRectangle(30.27, 36.83, 69.64, 63.03), width=42.0, height=6.0)
        (found,) = self.tool._all([position])
        self.assertAlmostEqual(found.rect.width(), 42.0)
        self.assertAlmostEqual(found.rect.height(), 6.0)
        self.assertAlmostEqual(found.rect.center().x(), 49.955, places=3)
        self.assertAlmostEqual(found.angle, -30.0, msg="30 grader medurs är -30 moturs")
        flat = SimpleNamespace(layerID=self.layer.id(), featureId=self.prop.id(), isUnplaced=False,
                               labelRect=QgsRectangle(0, 0, 10, 5))
        self.layer.changeAttributeValue(self.prop.id(), self.layer.fields().indexOf("label_rot"), None)
        (unturned,) = self.tool._all([flat])
        self.assertEqual((unturned.angle, unturned.rect.width()), (0.0, 10.0))


class ToolBarLabelTests(GuiCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def test_the_text_button_has_an_icon_and_is_a_click_tool_that_excludes_the_others(self):
        self.assertFalse(self.toolbar.act_label.icon().isNull())
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        pump()
        self.assertTrue(self.toolbar.act_label.isEnabled())
        self.toolbar.act_label.trigger()
        self.assertIs(self.canvas.mapTool(), self.toolbar.label_tool)
        self.assertTrue(self.toolbar.act_label.isChecked())
        self.toolbar.act_select.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.assertFalse(self.toolbar.act_select.isChecked())
        self.toolbar.act_assign.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.toolbar.act_fill_property.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.toolbar.draw_actions["anvandning_yta"].trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())

    def test_the_text_button_needs_a_plan_and_a_running_edit_session(self):
        self.assertFalse(self.toolbar.act_label.isEnabled(), "ingen redigeringssession än")
        self.toolbar.start()
        pump()
        self.assertTrue(self.toolbar.act_label.isEnabled())
        self.toolbar.act_label.trigger()
        self.controller.stop_editing(save=False)
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_label.isEnabled())
        self.assertFalse(self.toolbar.act_label.isChecked())
        QgsProject.instance().clear()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_label.isEnabled())

    def test_the_icon_is_valid_svg(self):
        import xml.etree.ElementTree as ET
        from rita_detaljplan.gui.plan_toolbar import ICONS
        self.assertTrue(ET.parse(ICONS / "text.svg").getroot().tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
