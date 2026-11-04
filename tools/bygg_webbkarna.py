"""Paketerar programmets kärna för webbsidan *Tagga planbeskrivning* (ritaplan.xyz) som en zip-fil.

    python tools/bygg_webbkarna.py <utfil.zip>

Zip-filen packas upp i webbläsaren med Pyodide (Python i webbläsaren). Den innehåller kärnan (``pbkarna``), sessionen
(``pbapp/session.py``, utan Qt) och webbgränssnittet (``pbweb``), plus ``VERSION.json`` med vilken version och commit av
Rita Detaljplan den är byggd av, så att sidan kan visa det. Samma kod som körs i QGIS: ingen kopia att hålla i synk.
Kör om skriptet och lägg den nya zip-filen på webbsidan när programmet ändras.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAKET = ROOT / "rita_detaljplan"
FASTA = (
    "rita_detaljplan/__init__.py",
    "rita_detaljplan/planbeskrivning/__init__.py",
    "rita_detaljplan/planbeskrivning/pbapp/__init__.py",
    "rita_detaljplan/planbeskrivning/pbapp/session.py",
)
MAPPAR = ("rita_detaljplan/planbeskrivning/pbkarna", "rita_detaljplan/planbeskrivning/pbweb")


def filer() -> list[str]:
    found = list(FASTA)
    for mapp in MAPPAR:
        found += sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / mapp).glob("*.py"))
    return found


def version_json() -> dict:
    metadata = (PAKET / "metadata.txt").read_text(encoding="utf-8")
    plugin = re.search(r"^version=(.+)$", metadata, re.MULTILINE)
    program = re.search(r'^VERSION = "(.+)"', (PAKET / "planbeskrivning/pbapp/__init__.py").read_text(encoding="utf-8"),
                        re.MULTILINE)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        andrad = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "rita_detaljplan"],
                                     capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, andrad = "", False
    return {"rita_detaljplan": plugin.group(1).strip() if plugin else "", "program": program.group(1) if program else "",
            "commit": commit, "andrade_filer": andrad}


def main(ut: Path) -> None:
    with zipfile.ZipFile(ut, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for fil in filer():
            zip_file.write(ROOT / fil, fil)
        zip_file.writestr("VERSION.json", json.dumps(version_json(), ensure_ascii=False, indent=1))
    print(f"Skrev {ut}: {len(filer())} filer, {ut.stat().st_size // 1024} kB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
