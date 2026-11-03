"""Skapar SQL för ett testschema i PostGIS med flera planer, så att en planmosaik i en webbkarta har något att visa.

Utgår från en plan i en GeoPackage (demoplanen) och gör kopior av den med olika status. De tre första ligger kant i kant och
delar planområdesgräns: planområdet är en trapets, så den andra planen är första planen vänd 180 grader runt mittpunkten
på kanten de delar, och den tredje delar den andra planens motsatta kant. Tabellerna skapas med pluginets egen ``ensure_schema``, så de får samma form som när
pluginet skapar en plan i PostGIS. Skriptet ansluter inte till någon databas: det skriver bara SQL till en fil.

    python-qgis.bat testmiljo/webbkarta/skapa_testschema.py <plan.gpkg> <ut.sql> [schema] [adress till handlingarna]

Varje plan får också tre handlingar i tabellen dokument: plankarta, planbeskrivning och ett planeringsunderlag. Länkarna
är <adress>/<plan-id>/plankarta.pdf och så vidare; filerna görs av handlingar/bygg_handlingar.py.
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rita_detaljplan.core import model, storage  # noqa: E402

# Kanterna som planerna delar, i demoplanens koordinater (SWEREF 99 13 30). Planområdets västra kant går mellan A och B,
# den östra mellan C och D (kanterna är raka: hörnen efter dem är rundade). Delas kanten A-B med en plan som är vänd 180 grader runt dess mittpunkt M ligger planerna kant
# i kant. Den tredje planen är den första förskjuten 2 * (M - N), där N är mitten på C-D: den delar då den andras östra kant.
A, B = (128536.756, 6488030.509), (128607.536, 6488171.292)
C, D = (128730.111, 6488107.563), (128651.357, 6487972.139)
M = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
N = ((C[0] + D[0]) / 2, (C[1] + D[1]) / 2)
SHIFT = (2 * (M[0] - N[0]), 2 * (M[1] - N[1]))
SOUTH = (0.0, -250.0)  # planer som inte är offentliga läggs en bit söderut

# plan-id, namn, status, förflyttning (("vänd", x, y) = 180 grader runt punkten, ("flytta", dx, dy)), antagande, laga kraft
PLANER = (
    ("demo_dp_01", "Demo detaljplan 01", "laga kraft", (), "2024-03-18", "2024-04-15"),
    ("demo_dp_02", "Demo detaljplan 02", "laga kraft", (("vänd", *M),), "2025-06-10", "2025-07-02"),
    ("demo_dp_03", "Demo detaljplan 03", "antagen", (("flytta", *SHIFT),), "2026-09-22", None),
    ("demo_dp_04", "Demo detaljplan 04", "samråd", (("flytta", *SOUTH),), None, None),
    ("demo_dp_05", "Demo detaljplan 05", "upphävd", (("vänd", *M), ("flytta", *SOUTH)), "2012-11-05", "2012-12-01"),
)
# Motiv som demoplanen saknar (demoplanens egna ligger kvar). Från planbeskrivningen till demoplanen.
EXTRA_MOTIV = {
    "GATA": "Gatan behövs för att ge de boende, besökarna och leveranserna en trafiksäker infart till kvarteret. Den "
            "utformas för både fordon och gång- och cykeltrafik.",
    "H": "Handel i bottenvåningen mot gatan ger service nära bostäderna och gör gatumiljön mer levande.",
    "q1": "Kvarterets trädgårdsmiljö är en del av områdets karaktär och ska bevaras i sitt ursprungliga skick.",
}
HANDLINGAR = (  # roll, innehåll, huvudområde, underlagstyp, namn, fil
    ("beslutshandling", "plankarta", None, None, "Plankarta", "plankarta.pdf"),
    ("planbeskrivning", None, None, None, "Planbeskrivning", "planbeskrivning.pdf"),
    ("planeringsunderlag", None, "utredningar", "dagvattenutredning", "Dagvattenutredning", "dagvattenutredning.pdf"),
)
GRID = 0.001  # alla koordinater avrundas till millimeter, så att delade kanter får exakt samma hörn
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


def main(gpkg: Path, out: Path, schema: str, document_base: str) -> None:
    db = sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    epsg = int(db.execute("select value from dp_meta where key = 'epsg'").fetchone()[0])
    meta = {r["key"]: r["value"] for r in db.execute("select key, value from dp_meta")
            if r["key"] in ("kommun", "kommunkod")}
    geometry_column = {r["table_name"]: r["column_name"]
                       for r in db.execute("select table_name, column_name from gpkg_geometry_columns")}
    have = {r[0] for r in db.execute("select name from sqlite_master where type = 'table'")}
    sql = ["BEGIN", *storage.ensure_schema(schema, epsg)]
    # Gör om planerna rent: raderna för demoplanerna tas bort innan de läggs in igen
    plan_list = ", ".join(storage.literal(plan[0]) for plan in PLANER)
    for table in [layer.name for layer in model.LAYERS] + [model.META_TABLE]:
        sql.append(f"DELETE FROM {storage.quote(schema)}.{storage.quote(table)} WHERE \"plan\" IN ({plan_list})")
    sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote(storage.SCHEMA_TABLE)} (\"key\", \"value\") VALUES "
               f"('schema_version', {storage.literal(str(model.SCHEMA_VERSION))}), ('epsg', {storage.literal(str(epsg))}) "
               "ON CONFLICT (\"key\") DO NOTHING")

    for plan, name, status, moves, adopted, in_force in PLANER:
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
                if layer.name == "bestammelse" and not data.get("motiv") and data.get("beteckning") in EXTRA_MOTIV:
                    data["motiv"] = EXTRA_MOTIV[data["beteckning"]]
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
                    geometry = f"ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromWKB(decode('{wkb}', 'hex')), {epsg})))"
                    for move in moves:
                        if move[0] == "vänd":
                            geometry = f"ST_Rotate({geometry}, pi(), {move[1]!r}, {move[2]!r})"
                        else:
                            geometry = f"ST_Translate({geometry}, {move[1]!r}, {move[2]!r})"
                    values.insert(1, f"ST_SnapToGrid({geometry}, {GRID})")
                statements.append("(" + ", ".join(values) + ")")
            sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote(layer.name)} ({', '.join(names)}) VALUES\n"
                       + ",\n".join(statements))
        for role, content, area, kind, title, file in HANDLINGAR:
            document = {"detaljplan": plan_id, "roll": role, "innehall": content, "huvudomrade": area, "underlagstyp": kind,
                        "namn": title, "kortnamn": title, "datum": in_force or adopted,
                        "lank": f"{document_base.rstrip('/')}/{plan}/{file}"}
            columns = ", ".join(['"plan"'] + [storage.quote(k) for k in document])
            values = ", ".join([storage.literal(plan)] + [storage.literal(v) if v else "NULL" for v in document.values()])
            sql.append(f"INSERT INTO {storage.quote(schema)}.{storage.quote('dokument')} ({columns}) VALUES ({values})")
    sql.append("COMMIT")
    out.write_text(";\n".join(sql) + ";\n", encoding="utf-8")
    print(f"Skrev {out} ({len(sql)} satser, schema {schema}, EPSG:{epsg}, {len(PLANER)} planer)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "detaljplaner_test",
         sys.argv[4] if len(sys.argv) > 4 else "https://example.org/handlingar")
