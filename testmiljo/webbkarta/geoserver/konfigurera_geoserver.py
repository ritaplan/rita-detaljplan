"""Ställer in GeoServer för planmosaiken via REST: arbetsyta, databaskoppling, tre lager med stil och en lagergrupp.

Kan köras om (det som redan finns hoppas över, stilarna uppdateras). Körs på servern, där GeoServers administration nås
på 127.0.0.1:8081:

    python3 geoserver/konfigurera_geoserver.py

Lösenorden läses ur .env och skrivs aldrig ut.
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = {}
for line in (HERE.parent / ".env").read_text().splitlines():
    if "=" in line:
        key, _, val = line.partition("=")
        ENV[key.strip()] = val.strip()

BASE = "http://127.0.0.1:8081/geoserver/rest"
GWC = "http://127.0.0.1:8081/geoserver/gwc/rest"  # cachen (GeoWebCache), som levererar vektorrutorna
AUTH = "Basic " + base64.b64encode(f"admin:{ENV['GEOSERVER_ADMIN_PASSWORD']}".encode()).decode()
WORKSPACE, STORE = "planmosaik", "publicering"
# Lagren i ritordning, underst först. Stilen heter som lagret (planmosaik/<lager>.sld)
LAYERS = (("plan_anvandning", "Användningsytor"), ("plan_egenskap", "Egenskapsytor"), ("plan_gransar", "Gränslinjer"))
# Lager som inte ritas i kartan utan bara frågas av informationsrutan (planområden med plandata och bestämmelser med motiv)
INFO_LAYERS = (("planmosaik", "Planområden"), ("plan_bestammelser", "Bestämmelser med motiv"))
GROUP = "planmosaik_karta"
# Cachen (vektorrutorna) levererar bara rutor inom lagergruppens utbredning, och den räknas ut första gången. Ange kommunens
# utbredning här (planschemats koordinatsystem: minx, miny, maxx, maxy), så att nya planer utanför den första inte får
# rutor som saknas. Tomma rutor kostar nästan ingenting.
EXTENT = (123500, 6483000, 134500, 6493500)
EPSG = "EPSG:3008"


def call(method, path, body=None, content_type="application/json", base=BASE):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Authorization": AUTH, "Content-Type": content_type,
                                              "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]


def step(text, result, ok=(200, 201)):
    code, answer = result
    state = "ok" if code in ok else f"FEL {code}: {answer}"
    print(f"{text}: {state}")
    if code not in ok:
        sys.exit(1)


step("GeoServer svarar", call("GET", "/about/version.json"))
if call("GET", f"/workspaces/{WORKSPACE}.json")[0] == 404:
    step("arbetsyta", call("POST", "/workspaces", {"workspace": {"name": WORKSPACE}}))
else:
    print("arbetsyta: finns redan")

parameters = {"host": "postgis", "port": "5432", "database": "gis", "schema": "publicering", "dbtype": "postgis",
              "user": "karta_ro", "passwd": ENV["KARTA_RO_PASSWORD"], "SSL mode": "REQUIRE",
              "Expose primary keys": "true", "validate connections": "true", "Loose bbox": "true",
              "min connections": "1", "max connections": "6"}
store = {"dataStore": {"name": STORE, "connectionParameters": {"entry": [{"@key": k, "$": v}
                                                                          for k, v in parameters.items()]}}}
if call("GET", f"/workspaces/{WORKSPACE}/datastores/{STORE}.json")[0] == 404:
    step("databaskoppling", call("POST", f"/workspaces/{WORKSPACE}/datastores", store))
else:
    step("databaskoppling (uppdaterad)", call("PUT", f"/workspaces/{WORKSPACE}/datastores/{STORE}", store))

for name, title in LAYERS + INFO_LAYERS:
    if call("GET", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{name}.json")[0] == 404:
        feature_type = {"featureType": {"name": name, "nativeName": name, "title": title,
                                        "srs": "EPSG:3008", "projectionPolicy": "FORCE_DECLARED", "enabled": True}}
        step(f"{name}: lager", call("POST", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes", feature_type))
        step(f"{name}: utbredning", call("PUT", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{name}"
                                                "?recalculate=nativebbox,latlonbbox", {"featureType": {"name": name}}))
    else:
        print(f"{name}: lager finns redan")
    if (name, title) in INFO_LAYERS:
        continue
    sld = (HERE / f"{name}.sld").read_bytes()
    if call("GET", f"/workspaces/{WORKSPACE}/styles/{name}.json")[0] == 404:
        step(f"{name}: stil", call("POST", f"/workspaces/{WORKSPACE}/styles?name={name}", sld,
                                   "application/vnd.ogc.sld+xml"))
    else:
        step(f"{name}: stil (uppdaterad)", call("PUT", f"/workspaces/{WORKSPACE}/styles/{name}", sld,
                                                "application/vnd.ogc.sld+xml"))
    step(f"{name}: standardstil", call("PUT", f"/layers/{WORKSPACE}:{name}",
                                       {"layer": {"defaultStyle": {"name": f"{WORKSPACE}:{name}"}}}))

# Lagergruppen ritar de tre lagren i rätt ordning som ett enda lager: LAYERS=planmosaik_karta
group = {"layerGroup": {
    "name": GROUP, "title": "Planmosaik", "mode": "SINGLE", "workspace": {"name": WORKSPACE},
    "bounds": {"minx": EXTENT[0], "miny": EXTENT[1], "maxx": EXTENT[2], "maxy": EXTENT[3], "crs": EPSG},
    "publishables": {"published": [{"@type": "layer", "name": f"{WORKSPACE}:{n}"} for n, _ in LAYERS]},
    "styles": {"style": [{"name": f"{WORKSPACE}:{n}"} for n, _ in LAYERS]}}}
if call("GET", f"/workspaces/{WORKSPACE}/layergroups/{GROUP}.json")[0] == 404:
    step("lagergrupp", call("POST", f"/workspaces/{WORKSPACE}/layergroups", group))
else:
    step("lagergrupp (uppdaterad)", call("PUT", f"/workspaces/{WORKSPACE}/layergroups/{GROUP}", group))

# Vektorrutor (MVT, kräver tillägget vectortiles): lagergruppen får formatet i cachen. Rutorna kommer ur cachen, så de
# förnyas efter en minut (0 = aldrig): en ny incheckning syns då snart i kartan. En ruta i taget (ingen metatiling).
tile_layer = f"""<GeoServerLayer><name>{WORKSPACE}:{GROUP}</name><enabled>true</enabled>
<mimeFormats><string>image/png</string><string>application/vnd.mapbox-vector-tile</string></mimeFormats>
<gridSubsets><gridSubset><gridSetName>EPSG:900913</gridSetName></gridSubset></gridSubsets>
<metaWidthHeight><int>1</int><int>1</int></metaWidthHeight><expireCache>60</expireCache><expireClients>0</expireClients>
</GeoServerLayer>"""
step("vektorrutor i cachen", call("PUT", f"/layers/{WORKSPACE}:{GROUP}.xml", tile_layer.encode(), "application/xml", GWC))
# Töm cachen för lagergruppen: rutor som redan sparats gäller den gamla utbredningen och de gamla planerna
truncate = f"<truncateLayer><layerName>{WORKSPACE}:{GROUP}</layerName></truncateLayer>"
step("cachen tömd", call("POST", "/masstruncate", truncate.encode(), "text/xml", GWC))

# Använd X-Forwarded-*-huvudena från nginx när GeoServer bygger adresser i kapabiliteterna
step("proxyadresser", call("PUT", "/settings", {"global": {"useHeadersProxyURL": True}}))
