"""Skapar SQL för ett testschema i PostGIS med flera planer, så att en planmosaik i en webbkarta har något att visa.

Utgår från en plan i en GeoPackage (demoplanen) och gör kopior av den, förskjutna i sidled och med olika status, så att
de hamnar bredvid varandra. Tabellerna skapas med pluginets egen ``ensure_schema``, så de får samma form som när
pluginet skapar en plan i PostGIS. Skriptet ansluter inte till någon databas: det skriver bara SQL till en fil.

    python-qgis.bat testmiljo/webbkarta/skapa_testschema.py <plan.gpkg> <ut.sql> [schema]
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rita_detaljplan.core import model, storage  # noqa: E402

# plan-id, namn, status, steg i sidled (i planbredder), steg i höjdled, antagande, laga kraft
PLANER = (
    ("demo_dp_01", "Demo detaljplan 01", "laga kraft", 0, 0, "2024-03-18", "2024-04-15"),
    ("demo_dp_02", "Demo detaljplan 02", "laga kraft", 1, 0, "2025-06-10", "2025-07-02"),
    ("demo_dp_03", "Demo detaljplan 03", "antagen", 2, 0, "2026-09-22", None),
    ("demo_dp_04", "Demo detaljplan 04", "samråd", 0, -1, None, None),
    ("demo_dp_05", "Demo detaljplan 05", "upphävd", 1, -1, "2012-11-05", "2012-12-01"),
)
SPACING = 1.1  # mellanrum mellan planerna, i planbredder
NAMESPACE = uuid.UUID("0b2d4a3e-7a39-4cc3-9f0e-5f6c2c1d7a10")


def wkb_of(blob: bytes) -> bytes:
    """GeoPackage-geometrin är WKB med ett huvud (magic, version, flaggor, SRS-id och ev. omslutande rektangel)."""
    envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
    return blob[8 + envelope:]


def value(field_type: str, raw) -> str:
    if raw is None or raw == "":
        return "NULL"
    if field_type == model.BOOL:
        return "true" if raw else "false"
    if field_type in (model.INT, model.REAL):
        return repr(raw)
    return storage.literal(raw)


def main(gpkg: Path, out: Path, schema: str) -> None:
    db = sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    epsg = int(db.execute("select value from dp_meta where key = 'epsg'").fetchone()[0])
    meta = {r["key"]: r["value"] for r in db.execute("select key, value from dp_meta")
            if r["key"] in ("kommun", "kommunkod")}
    geometry_column = {r["table_name"]: r["column_name"]
                       for r in db.execute("select table_name, column_name from gpkg_geometry_columns")}
    x0, y0, x1, y1 = db.execute("select min_x, min_y, max_x, max_y from gpkg_contents "
                                "where table_name = 'detaljplan'").fetchone()
    width, height = (x1 - x0) * SPACING, (y1 - y0) * SPACING
    have = {r[0] for r in db.execute("select name from sqlite_master where type = 'table'")}
    sql = ["BEGIN", *storage.ensure_schema(schema, epsg)]
    sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote(storage.SCHEMA_TABLE)} (\"key\", \"value\") VALUES "
               f"('schema_version', {storage.literal(str(model.SCHEMA_VERSION))}), ('epsg', {storage.literal(str(epsg))}) "
               "ON CONFLICT (\"key\") DO NOTHING")

    for plan, name, status, step_x, step_y, adopted, in_force in PLANER:
        ids: dict[str, str] = {}

        def new_id(old) -> str:
            return ids.setdefault(old, str(uuid.uuid5(NAMESPACE, f"{plan}:{old}")))

        plan_id = str(uuid.uuid5(NAMESPACE, f"{plan}:detaljplan"))
        meta_rows = {"spec_version": model.SPEC_VERSION, **meta}
        sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote(model.META_TABLE)} (\"plan\", \"key\", \"value\") "
                   "VALUES " + ", ".join(f"({storage.literal(plan)}, {storage.literal(k)}, {storage.literal(v)})"
                                         for k, v in meta_rows.items()))
        for layer in model.LAYERS:
            if layer.name not in have:
                continue
            rows = db.execute(f"select * from {storage.quote(layer.name)}").fetchall()
            if not rows:
                continue
            fields = {f.name: f.type for f in layer.fields}
            columns = [c for c in rows[0].keys() if c in fields]
            names = ['"plan"'] + [storage.quote(c) for c in columns]
            if layer.geometry:
                names.insert(1, '"geom"')
            statements = []
            for row in rows:
                data = {c: row[c] for c in columns}
                if layer.name == "detaljplan":
                    data.update(objektidentitet=plan_id, namn=name, status=status, beteckning=name.replace("Demo detaljplan ", "Dp "),
                                datumStatusforandring=in_force or adopted)
                else:
                    if "objektidentitet" in data:
                        data["objektidentitet"] = new_id(data["objektidentitet"])
                    if "yta" in data and data["yta"]:
                        data["yta"] = new_id(data["yta"])
                    if "detaljplan" in data:
                        data["detaljplan"] = plan_id
                    if layer.name == "beslutsinformation":
                        data.update(datumAntagande=adopted, datumLagakraft=in_force, genomforandetid=60,
                                    diarienummerKommun=f"2026/{plan[-2:]}")
                values = [storage.literal(plan)] + [value(fields[c], data[c]) for c in columns]
                if layer.geometry:
                    wkb = wkb_of(row[geometry_column[layer.name]]).hex()
                    dx, dy = step_x * width, step_y * height
                    values.insert(1, f"ST_Translate(ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromWKB(decode('{wkb}', 'hex')), "
                                     f"{epsg}))), {dx!r}, {dy!r})")
                statements.append("(" + ", ".join(values) + ")")
            sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote(layer.name)} ({', '.join(names)}) VALUES\n"
                       + ",\n".join(statements))
    sql.append("COMMIT")
    out.write_text(";\n".join(sql) + ";\n", encoding="utf-8")
    print(f"Skrev {out} ({len(sql)} satser, schema {schema}, EPSG:{epsg}, {len(PLANER)} planer)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "detaljplaner_test")
