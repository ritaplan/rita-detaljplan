"""Gör en plankarta (PDF) per plan ur samma karta som visas i webbkartan: QGIS Server ritar planen som PDF.

Gör en karta för varje offentlig plan (vyn publicering.planmosaik). Körs på servern, i mappen med docker-compose.yml:

    python3 handlingar/bygg_plankartor.py <utmapp>

Skriver <utmapp>/<plan-id>/plankarta.pdf. En förenklad plankarta utan teckenförklaring, bara för testmiljön: en riktig
plankarta exporteras ur Rita Detaljplan (Leverans och export) och läggs ut av kommunen.
"""
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1])
# En egen, kortlivad QGIS Server: ett filter (FILTER) i QGIS Server blir kvar i processens cachade projekt och påverkar
# senare anrop, så det får aldrig köras mot den publika tjänsten.
IMAGE = "qgis/qgis-server:4.2.3-resolute"
CONTAINER = "planmosaik-plankarta"
SERVICE = "http://127.0.0.1:8095/ows/"
HERE = Path.cwd()
MARGIN = 25  # meter runt planen
PX_PER_M = 5  # bildens upplösning: 5 px per meter (planen ritas då i skala runt 1:1000 på papper)


def query(sql: str) -> list[list[str]]:
    result = subprocess.run(["docker", "exec", "postgis", "sh", "-c",
                             'psql -U "$POSTGRES_USER" -d gis -At -F "|" -c "' + sql.replace('"', '\\"') + '"'],
                            capture_output=True, text=True, check=True)
    return [line.split("|") for line in result.stdout.splitlines() if line]


def start_server() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--rm", "--name", CONTAINER, "--network", "postgis_default", "--memory", "512m",
                    "-e", "QGIS_PROJECT_FILE=/io/data/planmosaik.qgs", "-v", f"{HERE}/qgis:/io/data:ro",
                    "-v", f"{HERE}/qgis/pg_service.conf:/etc/postgresql-common/pg_service.conf:ro",
                    "-p", "127.0.0.1:8095:80", IMAGE], check=True, capture_output=True)
    for _ in range(40):
        try:
            urllib.request.urlopen(SERVICE + "?SERVICE=WMS&REQUEST=GetCapabilities", timeout=5).read()
            return
        except OSError:
            time.sleep(1)
    sys.exit("QGIS Server för plankartorna startade inte")


start_server()
try:
    for plan, minx, miny, maxx, maxy, real_width, real_height in query(
            f"select plan, st_xmin(e), st_ymin(e), st_xmax(e), st_ymax(e), st_xmax(r) - st_xmin(r), st_ymax(r) - st_ymin(r) "
            f"from (select plan, st_extent(st_transform(geom, 3857)) e, st_extent(geom) r from publicering.planmosaik "
            f"group by plan) x order by plan"):
        minx, miny, maxx, maxy, real_width, real_height = map(float, (minx, miny, maxx, maxy, real_width, real_height))
        # Web Mercator-meter är längre än verkliga meter: marginalen och bildens storlek räknas om till verkliga mått
        stretch_x, stretch_y = (maxx - minx) / real_width, (maxy - miny) / real_height
        minx, maxx = minx - MARGIN * stretch_x, maxx + MARGIN * stretch_x
        miny, maxy = miny - MARGIN * stretch_y, maxy + MARGIN * stretch_y
        width = round((real_width + 2 * MARGIN) * PX_PER_M)
        height = round((real_height + 2 * MARGIN) * PX_PER_M)
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "FORMAT": "application/pdf", "STYLES": "",
                  "LAYERS": "plan_anvandning,plan_egenskap,plan_gransar", "CRS": "EPSG:3857", "TRANSPARENT": "FALSE",
                  "BBOX": f"{minx},{miny},{maxx},{maxy}", "WIDTH": width, "HEIGHT": height, "DPI": 150,
                  # bara den här planens ytor. Gränslinjerna filtreras inte: planområdesgränsen hör inte till en enskild plan, och
                  # QGIS Server tillåter varken OR eller funktioner i ett filter. Grannplanernas gränser syns därför i marginalen.
                  "FILTER": ";".join(f"{layer}:\"plan\" = '{plan}'" for layer in ("plan_anvandning", "plan_egenskap"))}
        folder = OUT / plan
        folder.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SERVICE + "?" + urllib.parse.urlencode(params), timeout=120) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            sys.exit(f"{plan}: inget PDF-svar: {data[:200]!r}")
        (folder / "plankarta.pdf").write_bytes(data)
        print(f"{plan}: plankarta.pdf ({len(data) // 1024} kB)")
finally:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
