"""Kontrollerar att filerna som är speglade mellan Rita Detaljplan och Rita Översiktsplan inte glidit isär.

Några moduler finns i båda pluginen med nästan samma innehåll (arkivpaketet, NGP-klienten, dialogerna för leverans och
inställningar m.fl.). Ändrar man en av dem ska den andra normalt följa med. Skriptet byter pluginens namn mot ett
gemensamt (så att ``detaljplan``/``oversiktsplan`` inte räknas som skillnad), jämför filerna och jämför skillnaderna
med dem som sparades sist (``tools/mirror_baseline.json``). Är en skillnad ny har den ena filen ändrats utan den andra.

    python tools/check_mirror.py              # jämför, avslutar med 1 om skillnaderna ändrats
    python tools/check_mirror.py --show       # skriver också ut skillnaderna
    python tools/check_mirror.py --update     # godkänner nuläget (efter att du gått igenom skillnaderna)

Rita Översiktsplan antas ligga bredvid, i ``../rita-oversiktsplan`` (eller i den mapp som anges med ``--other``).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).resolve().parent / "mirror_baseline.json"
# filer som finns i båda pluginen med nästan samma innehåll, relativt pluginmappen
MIRRORED = (
    "core/archive.py", "core/ngp_client.py", "core/kommuner.py", "core/importer.py",
    "gui/messages.py", "gui/kommun_combo.py", "gui/delivery_dialog.py", "gui/about_dialog.py",
    "gui/settings_dialog.py", "gui/import_dialog.py",
)
# gui/postgis_plan_dialog.py (ÖP) är i Rita Detaljplan databashanteraren (gui/database_manager_dialog.py), som ännu inte finns i
# Rita Översiktsplan
_NAMES = ((re.compile(r"rita_detaljplan|rita_oversiktsplan"), "rita_X"),
          (re.compile(r"detaljplan|oversiktsplan", re.I), "X"),
          (re.compile(r"Översiktsplan|översiktsplan", re.I), "X"),
          (re.compile(r"\bÖP\b|\bDP\b"), "X"))


def normalise(text: str) -> list[str]:
    """Raderna med pluginets namn utbytt mot ``X`` (och radslut normaliserade)."""
    for pattern, replacement in _NAMES:
        text = pattern.sub(replacement, text)
    return text.replace("\r\n", "\n").split("\n")


def difference(mine: Path, other: Path) -> list[str]:
    """Skillnaderna mellan två filer som radlista (``-`` och ``+``), utan filhuvudet."""
    a, b = normalise(mine.read_text(encoding="utf-8")), normalise(other.read_text(encoding="utf-8"))
    return [line for line in difflib.unified_diff(a, b, lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def fingerprint(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def compare(mine_dir: Path, other_dir: Path) -> dict:
    """Per fil: antal skiljande rader, ett fingeravtryck av skillnaderna och skillnaderna själva."""
    result = {}
    for name in MIRRORED:
        mine, other = mine_dir / name, other_dir / name
        if not mine.is_file() or not other.is_file():
            result[name] = {"missing": True, "lines": 0, "fingerprint": "saknas", "diff": []}
            continue
        diff = difference(mine, other)
        result[name] = {"missing": False, "lines": len(diff), "fingerprint": fingerprint(diff), "diff": diff}
    return result


def changed_since_baseline(result: dict, baseline: dict) -> list[str]:
    """Filerna vars skillnader inte är de som sparades sist."""
    return [name for name, info in result.items() if baseline.get(name, {}).get("fingerprint") != info["fingerprint"]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--other", type=Path, default=ROOT.parent / "rita-oversiktsplan", help="Rita Översiktsplans mapp")
    parser.add_argument("--show", action="store_true", help="skriv ut skillnaderna")
    parser.add_argument("--update", action="store_true", help="spara nuläget som godkänt")
    args = parser.parse_args(argv)
    other_dir = args.other / "rita_oversiktsplan"
    if not other_dir.is_dir():
        print(f"Hittar inte Rita Översiktsplan i {args.other}. Ange mappen med --other.")
        return 2
    result = compare(ROOT / "rita_detaljplan", other_dir)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}
    changed = changed_since_baseline(result, baseline)
    for name, info in result.items():
        mark = "ändrad sedan sist" if name in changed else "som sist"
        print(f"{name:34s} {info['lines']:4d} skiljande rader  {mark}")
        if args.show and info["diff"] and (name in changed or args.update):
            for line in info["diff"][:60]:
                print("    " + line[:150])
            if len(info["diff"]) > 60:
                print(f"    ... och {len(info['diff']) - 60} rader till")
    if args.update:
        BASELINE.write_text(json.dumps({n: {"lines": i["lines"], "fingerprint": i["fingerprint"]} for n, i in result.items()},
                                       indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("Nuläget är sparat som godkänt.")
        return 0
    if changed:
        print("\nSkillnaderna mellan pluginen har ändrats i filerna ovan. Har en av dem ändrats utan den andra?\n"
              "Kör med --show för att se skillnaderna, för över ändringen till den andra och kör sedan med --update.")
        return 1
    print("\nInga nya skillnader.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
