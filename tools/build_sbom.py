"""Skapar materiallistan (SBOM) och kontrollsumman som hör till en release.

    python tools/build_sbom.py           # skriver dist/rita_detaljplan-<version>.sbom.cdx.json och .zip.sha256

SBOM:en följer CycloneDX 1.5 (JSON). Den beskriver pluginet, det som följer med i zip-filen (data från Boverket,
Lantmäteriet, SCB och Library of Congress) och det pluginet kräver men inte levererar (QGIS med Python, PyQt, GDAL).
Pluginet har inga andra beroenden: skriptet läser alla importer i koden och avbryter om det dyker upp ett paket som
inte är QGIS, standardbiblioteket eller PySide6 (valfritt, bara för det fristående taggningsprogrammet). Då måste
listan i ``KNOWN_THIRD_PARTY`` och dokumentet docs/sakerhet.md uppdateras medvetet. Zip-filen byggs först med
``tools/build_zip.py``; saknas den utelämnas dess kontrollsumma. Ingen QGIS behövs.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import build_zip

ROOT = build_zip.ROOT
PLUGIN = build_zip.PLUGIN
REPOSITORY = "https://github.com/ritaplan/rita-detaljplan"
KNOWN_THIRD_PARTY = {"qgis", "osgeo", "PySide6"}  # allt annat som importeras är ett nytt beroende
OPTIONAL = {"PySide6"}

# (sökväg under repots rot, namn, leverantör, licens/villkor, källa)
BUNDLED_DATA = [
    (f"{PLUGIN}/data/planbestammelsekatalog.json", "Planbestämmelsekatalogen", "Boverket", "Öppna data (källa anges)",
     "https://www.boverket.se/sv/om-boverket/oppna-data/planbestammelser/"),
    (f"{PLUGIN}/data/kommuner.json", "Kommunlista med kommunkoder", "SCB", "Öppen statistik (källa anges)",
     "https://api.scb.se"),
    (f"{PLUGIN}/data/schemas/detaljplan-4.1.json", "NGP Detaljplan 4.1, JSON-schema", "Lantmäteriet",
     "Lantmäteriets villkor", "https://www.lantmateriet.se"),
    (f"{PLUGIN}/data/schemas/geometri-2.0.json", "NGP Geometri 2.0, JSON-schema", "Lantmäteriet",
     "Lantmäteriets villkor", "https://www.lantmateriet.se"),
    (f"{PLUGIN}/data/schemas/geometrimetadata-2.0.1.json", "NGP Geometrimetadata 2.0.1, JSON-schema", "Lantmäteriet",
     "Lantmäteriets villkor", "https://www.lantmateriet.se"),
    (f"{PLUGIN}/data/schemas/premis-v3-0.xsd", "PREMIS 3.0 XML-schema", "Library of Congress",
     "Library of Congress villkor", "https://www.loc.gov/standards/premis/"),
    (f"{PLUGIN}/data/styles/detaljplaner-bfs-2020-6.xml", "Stilbibliotek Detaljplaner (BFS 2020:6)", "Alnemar", "CC0-1.0",
     "https://hub.qgis.org/styles/238/"),
]

# Krävs av pluginet men levereras inte med det: (namn, version, kommentar)
PLATFORM = [
    ("QGIS", ">=4.0", "Pluginet körs i QGIS och kräver 4.0 eller senare (qgisMinimumVersion i metadata.txt)."),
    ("Python", "(följer QGIS)", "Pythontolken som QGIS levererar. Pluginet använder bara standardbiblioteket."),
    ("PyQt6", "(följer QGIS)", "Qt-bindningen som QGIS levererar (qgis.PyQt)."),
    ("GDAL/OGR (osgeo)", "(följer QGIS)", "Läser och skriver GeoPackage."),
    ("PySide6", "(valfri)", "Bara för det fristående taggningsprogrammet (python -m rita_detaljplan.planbeskrivning)."
                            " Behövs inte i QGIS."),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def third_party_imports(root: Path = ROOT) -> set[str]:
    """Namnen på paket utanför standardbiblioteket som koden importerar (utom pluginets egna moduler)."""
    found = set()
    for path in (root / PLUGIN).rglob("*.py"):
        for match in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_]\w*)", path.read_text(encoding="utf-8"), re.M):
            name = match.group(1)
            if name not in sys.stdlib_module_names and name not in {PLUGIN, "__future__"}:
                found.add(name)
    return found


def check_dependencies(root: Path = ROOT) -> None:
    unknown = third_party_imports(root) - KNOWN_THIRD_PARTY
    if unknown:
        raise SystemExit("Koden importerar paket som inte finns i materiallistan: " + ", ".join(sorted(unknown))
                         + ". Lägg till dem i KNOWN_THIRD_PARTY och PLATFORM här och i docs/sakerhet.md.")


def build_sbom(root: Path = ROOT, zip_path: Path | None = None) -> dict:
    check_dependencies(root)
    meta = build_zip.read_metadata(root)
    version = build_zip.version(root)
    app_ref = f"pkg:github/ritaplan/rita-detaljplan@v{version}"
    hashes = [{"alg": "SHA-256", "content": sha256(zip_path)}] if zip_path is not None and zip_path.is_file() else []
    components, refs = [], []
    for relative, name, supplier, terms, source in BUNDLED_DATA:
        path = root / relative
        ref = f"file:{relative}"
        components.append({
            "type": "data", "bom-ref": ref, "name": name, "supplier": {"name": supplier},
            "hashes": [{"alg": "SHA-256", "content": sha256(path)}],
            "licenses": [{"license": {"name": terms}}],
            "externalReferences": [{"type": "website", "url": source}],
            "properties": [{"name": "path-in-package", "value": relative}],
        })
        refs.append(ref)
    for name, platform_version, note in PLATFORM:
        ref = f"platform:{name}"
        components.append({
            "type": "application" if name == "QGIS" else "library", "bom-ref": ref, "name": name,
            "version": platform_version, "description": note,
            "scope": "optional" if name in OPTIONAL else "required",
            "properties": [{"name": "bundled", "value": "false"}],
        })
        refs.append(ref)
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {
            "component": {
                "type": "application", "bom-ref": app_ref, "name": meta.get("name", "Rita Detaljplan"), "version": version,
                "description": "QGIS-plugin för detaljplaner", "purl": app_ref,
                "licenses": [{"license": {"id": "GPL-2.0-or-later"}}], "hashes": hashes,
                "supplier": {"name": "Eric Alnemar", "url": [meta.get("homepage", "https://ritaplan.xyz")]},
                "externalReferences": [{"type": "vcs", "url": REPOSITORY}, {"type": "website", "url": "https://ritaplan.xyz"},
                                       {"type": "issue-tracker", "url": REPOSITORY + "/issues"}],
            },
            "tools": {"components": [{"type": "application", "name": "tools/build_sbom.py"}]},
        },
        "components": components,
        "dependencies": [{"ref": app_ref, "dependsOn": refs}],
    }


def main() -> int:
    version = build_zip.version()
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"{PLUGIN}-{version}.zip"
    sbom_path = out_dir / f"{PLUGIN}-{version}.sbom.cdx.json"
    sbom_path.write_text(json.dumps(build_sbom(ROOT, zip_path), indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                         newline="\n")
    print(f"Skapade {sbom_path}")
    if zip_path.is_file():
        sums = out_dir / f"{zip_path.name}.sha256"
        sums.write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="utf-8", newline="\n")
        print(f"Skapade {sums}")
    else:
        print(f"{zip_path.name} finns inte (kör tools/build_zip.py först): ingen kontrollsumma skapades.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
