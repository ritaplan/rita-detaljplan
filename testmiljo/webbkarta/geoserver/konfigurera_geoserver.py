"""Ställer in GeoServer för planmosaiken via REST: arbetsyta, databaskoppling, lager och stil.

Kan köras om (det som redan finns hoppas över). Körs på servern, där GeoServers administration nås på 127.0.0.1:8081:

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
AUTH = "Basic " + base64.b64encode(f"admin:{ENV['GEOSERVER_ADMIN_PASSWORD']}".encode()).decode()
WORKSPACE, STORE, LAYER = "planmosaik", "publicering", "planmosaik"


def call(method, path, body=None, content_type="application/json"):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(BASE + path, data=data, method=method,
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
              "Expose primary keys": "true", "validate connections": "true", "Loose bbox": "true"}
store = {"dataStore": {"name": STORE, "connectionParameters": {"entry": [{"@key": k, "$": v}
                                                                          for k, v in parameters.items()]}}}
if call("GET", f"/workspaces/{WORKSPACE}/datastores/{STORE}.json")[0] == 404:
    step("databaskoppling", call("POST", f"/workspaces/{WORKSPACE}/datastores", store))
else:
    print("databaskoppling: finns redan")

if call("GET", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{LAYER}.json")[0] == 404:
    feature_type = {"featureType": {"name": LAYER, "nativeName": "planmosaik", "title": "Planmosaik",
                                    "abstract": "Detaljplaner som är antagna eller har vunnit laga kraft",
                                    "srs": "EPSG:3008", "projectionPolicy": "FORCE_DECLARED", "enabled": True}}
    step("lager", call("POST", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes", feature_type))
    step("utbredning", call("PUT", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{LAYER}"
                                    "?recalculate=nativebbox,latlonbbox", {"featureType": {"name": LAYER}}))
else:
    print("lager: finns redan")

sld = (HERE / "planmosaik.sld").read_bytes()
if call("GET", f"/workspaces/{WORKSPACE}/styles/planmosaik.json")[0] == 404:
    step("stil", call("POST", f"/workspaces/{WORKSPACE}/styles?name=planmosaik", sld,
                      "application/vnd.ogc.sld+xml"))
else:
    step("stil (uppdaterad)", call("PUT", f"/workspaces/{WORKSPACE}/styles/planmosaik", sld,
                                   "application/vnd.ogc.sld+xml"))
step("standardstil", call("PUT", f"/layers/{WORKSPACE}:{LAYER}",
                          {"layer": {"defaultStyle": {"name": f"{WORKSPACE}:planmosaik"}}}))
# Använd X-Forwarded-*-huvudena från nginx när GeoServer bygger adresser i kapabiliteterna
step("proxyadresser", call("PUT", "/settings", {"global": {"useHeadersProxyURL": True}}))
